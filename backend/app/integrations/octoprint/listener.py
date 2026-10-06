import asyncio
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import decrypt_secret
from app.db.models import JobStatus, Layer, Printer, PrinterStatus, PrintJob
from app.integrations.octoprint.client import OctoPrintClient
from app.ws.manager import manager

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 10


def _websocket_url(octoprint_url: str) -> str:
    parts = urlsplit(octoprint_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/sockjs/websocket", "", ""))


def _map_state_flags(flags: dict) -> PrinterStatus:
    if flags.get("error") or flags.get("closedOrError"):
        return PrinterStatus.error
    if flags.get("paused") or flags.get("pausing"):
        return PrinterStatus.paused
    if flags.get("printing"):
        return PrinterStatus.printing
    if flags.get("operational"):
        return PrinterStatus.idle
    return PrinterStatus.offline


async def run_printer_listener(printer_id: int, db_session_factory, redis_client) -> None:
    """Reconnect loop for a single printer's OctoPrint connection. Runs forever until cancelled;
    a bad URL/offline printer just retries instead of taking the whole backend down."""
    while True:
        try:
            await _listen_once(printer_id, db_session_factory, redis_client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("OctoPrint listener for printer %s failed, retrying in %ss", printer_id, _RECONNECT_DELAY_SECONDS)
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


async def _listen_once(printer_id: int, db_session_factory, redis_client) -> None:
    async with db_session_factory() as db:
        printer = await db.get(Printer, printer_id)
        if printer is None:
            return
        octoprint_url = printer.octoprint_url
        api_key = decrypt_secret(printer.octoprint_api_key_encrypted)

    client = OctoPrintClient(octoprint_url, api_key)
    login_info = await client.login()

    # Hydrate last_known_status immediately rather than waiting for the first WS push.
    try:
        printer_state = await client.get_printer_state()
        await _set_printer_status(db_session_factory, printer_id, _map_state_flags(printer_state.get("state", {}).get("flags", {})))
    except httpx.HTTPError:
        logger.warning("Could not fetch initial /api/printer state for printer %s", printer_id)

    ws_url = _websocket_url(octoprint_url)
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"auth": f"{login_info['name']}:{login_info['session']}"}))

        async for raw in ws:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            current = message.get("current")
            if current is not None:
                flags = current.get("state", {}).get("flags", {})
                await _set_printer_status(db_session_factory, printer_id, _map_state_flags(flags))

            plugin_message = message.get("plugin")
            # Field names (currentLayer/currentHeight) are DisplayLayerProgress's plugin message
            # shape as best remembered, not verified against a live instance - re-check once
            # real hardware + the real plugin are available.
            if plugin_message and plugin_message.get("plugin") == "DisplayLayerProgress":
                await _handle_layer_changed(db_session_factory, redis_client, printer_id, plugin_message.get("data", {}))


async def _set_printer_status(db_session_factory, printer_id: int, new_status: PrinterStatus) -> None:
    async with db_session_factory() as db:
        printer = await db.get(Printer, printer_id)
        if printer is not None and printer.last_known_status != new_status:
            printer.last_known_status = new_status
            await db.commit()
            # This listener runs inside the backend process, same as print_jobs/alerts -
            # broadcast directly, no Redis relay needed (that's only for other processes).
            await manager.broadcast("printer.status", {"printer_id": printer_id, "status": new_status.value})


async def _handle_layer_changed(db_session_factory, redis_client, printer_id: int, data: dict) -> None:
    layer_number = data.get("currentLayer")
    z_height = data.get("currentHeight")
    if layer_number is None or z_height is None:
        return

    try:
        layer_number = int(layer_number)
        z_height = Decimal(str(z_height))
    except (TypeError, ValueError, InvalidOperation):
        logger.warning("Discarding unparseable layer-changed payload for printer %s: %r", printer_id, data)
        return

    async with db_session_factory() as db:
        result = await db.execute(
            select(PrintJob.id).where(PrintJob.printer_id == printer_id, PrintJob.status == JobStatus.running)
        )
        job_id = result.scalar_one_or_none()
        if job_id is None:
            logger.warning("Layer change for printer %s with no running print job; skipping", printer_id)
            return

        layer = Layer(job_id=job_id, layer_number=layer_number, z_height=z_height)
        db.add(layer)
        try:
            await db.commit()
        except IntegrityError:
            # Duplicate plugin message (reconnect replay, retransmit) for a layer we already recorded.
            await db.rollback()

    await redis_client.publish(
        f"layer_ready:{printer_id}",
        json.dumps(
            {
                "printer_id": printer_id,
                "job_id": job_id,
                "layer_number": layer_number,
                "z_height": str(z_height),
            }
        ),
    )
