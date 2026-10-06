import asyncio
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import websockets
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import JobStatus, Layer, Printer, PrinterStatus, PrintJob
from app.schemas.print_job import PrintJobCreate
from app.services.print_jobs import create_print_job, transition_job_status
from app.ws.manager import manager

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 10
_SUBSCRIBE_ID = 1

# Klipper's print_stats.state -> our printer status.
_STATE_TO_PRINTER_STATUS = {
    "printing": PrinterStatus.printing,
    "paused": PrinterStatus.paused,
    "error": PrinterStatus.error,
    "standby": PrinterStatus.idle,
    "complete": PrinterStatus.idle,
    "cancelled": PrinterStatus.idle,
}

# Terminal Klipper states -> how the matching print job should be closed.
_STATE_TO_JOB_STATUS = {
    "complete": JobStatus.completed,
    "cancelled": JobStatus.cancelled,
    "error": JobStatus.failed,
}


def _websocket_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/websocket", "", ""))


class _PrinterState:
    """Moonraker pushes only the fields that changed, so each notification is a patch over
    the snapshot from the subscribe response - a layer-change notification carries no z_pos.
    Merging them here is what makes 'the layer changed, and z is X' answerable."""

    def __init__(self) -> None:
        self.state: str | None = None
        self.filename: str | None = None
        self.z_pos: Decimal | None = None
        self.layer: int | None = None
        self.layer_count: int | None = None
        self.layer_height: Decimal | None = None

    def merge(self, status: dict) -> None:
        print_stats = status.get("print_stats", {})
        virtual_sdcard = status.get("virtual_sdcard", {})

        if "state" in print_stats:
            self.state = print_stats["state"]
        if "filename" in print_stats:
            self.filename = print_stats["filename"]
        if print_stats.get("z_pos") is not None:
            try:
                self.z_pos = Decimal(str(print_stats["z_pos"])).quantize(Decimal("0.01"))
            except InvalidOperation:
                logger.warning("Unparseable z_pos from Moonraker: %r", print_stats["z_pos"])
        if virtual_sdcard.get("layer_count") is not None:
            self.layer_count = virtual_sdcard["layer_count"]
        if virtual_sdcard.get("layer") is not None:
            self.layer = virtual_sdcard["layer"]

        metadata = (virtual_sdcard.get("cur_print_data") or {}).get("metadata") or {}
        if metadata.get("layer_height") is not None:
            try:
                self.layer_height = Decimal(str(metadata["layer_height"]))
            except InvalidOperation:
                logger.warning("Unparseable layer_height from Moonraker: %r", metadata["layer_height"])

    def z_for_layer(self, layer_number: int) -> Decimal | None:
        """print_stats.z_pos on this firmware lags badly - measured holding 60.63 across layers
        324-326 while the toolhead was really at ~65.4, then jumping 5.2mm at once. layer x
        layer_height matches the toolhead's real Z, so prefer it and keep z_pos as fallback."""
        if self.layer_height is not None:
            return (self.layer_height * layer_number).quantize(Decimal("0.01"))
        return self.z_pos


async def run_moonraker_listener(printer_id: int, db_session_factory, redis_client) -> None:
    """Reconnect loop for a single printer's Moonraker connection. Runs forever until cancelled;
    a bad URL/offline printer just retries instead of taking the whole backend down."""
    while True:
        try:
            await _listen_once(printer_id, db_session_factory, redis_client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Moonraker listener for printer %s failed, retrying in %ss", printer_id, _RECONNECT_DELAY_SECONDS
            )
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


async def _listen_once(printer_id: int, db_session_factory, redis_client) -> None:
    async with db_session_factory() as db:
        printer = await db.get(Printer, printer_id)
        if printer is None:
            return
        base_url = printer.octoprint_url

    ws_url = _websocket_url(base_url)
    state = _PrinterState()

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "printer.objects.subscribe",
                    "params": {"objects": {"print_stats": None, "virtual_sdcard": None}},
                    "id": _SUBSCRIBE_ID,
                }
            )
        )
        logger.info("Moonraker listener for printer %s connected to %s", printer_id, ws_url)

        async for raw in ws:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if message.get("id") == _SUBSCRIBE_ID:
                state.merge(message.get("result", {}).get("status", {}))
                # Sync status and job, but not the layer: whatever layer was in progress when
                # we connected has already been captured or never will be, and re-publishing
                # it would duplicate work for a layer the nozzle has moved past. The job does
                # need syncing here, so attaching to a print already running (backend restart
                # mid-print) still records the remaining layers.
                await _sync_printer_status(db_session_factory, printer_id, state)
                await _sync_job(db_session_factory, printer_id, state)
                logger.info(
                    "Moonraker listener for printer %s baseline: state=%s layer=%s/%s z=%s",
                    printer_id,
                    state.state,
                    state.layer,
                    state.layer_count,
                    state.z_pos,
                )
                continue

            if message.get("method") != "notify_status_update":
                continue

            previous_state = state.state
            previous_layer = state.layer
            state.merge(message.get("params", [{}])[0])

            if state.state != previous_state:
                logger.info(
                    "Printer %s state: %s -> %s (file=%s)", printer_id, previous_state, state.state, state.filename
                )
                await _sync_printer_status(db_session_factory, printer_id, state)
                await _sync_job(db_session_factory, printer_id, state)

            if state.layer != previous_layer and state.state == "printing":
                await _handle_layer_change(db_session_factory, redis_client, printer_id, state)


async def _sync_printer_status(db_session_factory, printer_id: int, state: _PrinterState) -> None:
    new_status = _STATE_TO_PRINTER_STATUS.get(state.state or "", PrinterStatus.offline)
    async with db_session_factory() as db:
        printer = await db.get(Printer, printer_id)
        if printer is not None and printer.last_known_status != new_status:
            printer.last_known_status = new_status
            await db.commit()
            # Runs inside the backend process, same as the OctoPrint listener - broadcast
            # directly instead of going through the Redis relay other processes need.
            await manager.broadcast("printer.status", {"printer_id": printer_id, "status": new_status.value})


async def _running_job_id(db, printer_id: int) -> int | None:
    result = await db.execute(
        select(PrintJob.id).where(PrintJob.printer_id == printer_id, PrintJob.status == JobStatus.running)
    )
    return result.scalar_one_or_none()


async def _sync_job(db_session_factory, printer_id: int, state: _PrinterState) -> None:
    """Opens a job when the printer starts printing and closes it when Klipper reports a
    terminal state, so a print needs no manual bookkeeping to show up in the timeline."""
    async with db_session_factory() as db:
        job_id = await _running_job_id(db, printer_id)

        if state.state == "printing":
            if job_id is not None:
                return
            try:
                job = await create_print_job(
                    db,
                    printer_id,
                    PrintJobCreate(
                        file_name=(state.filename or "impresion_moonraker")[:255],
                        estimated_layers=state.layer_count,
                    ),
                )
            except HTTPException:
                logger.warning("Could not open a print job for printer %s", printer_id, exc_info=True)
                return
            logger.info("Opened print job %s for printer %s (%s)", job.id, printer_id, job.file_name)
            return

        new_job_status = _STATE_TO_JOB_STATUS.get(state.state or "")
        if new_job_status is None or job_id is None:
            return

        job = await db.get(PrintJob, job_id)
        try:
            await transition_job_status(db, job, new_job_status)
        except HTTPException:
            logger.warning("Could not close print job %s for printer %s", job_id, printer_id, exc_info=True)
            return
        logger.info("Closed print job %s for printer %s as %s", job_id, printer_id, new_job_status.value)


async def _handle_layer_change(db_session_factory, redis_client, printer_id: int, state: _PrinterState) -> None:
    layer_number = state.layer
    if layer_number is None or layer_number < 1:
        return

    z_height = state.z_for_layer(layer_number)
    if z_height is None:
        # Don't drop the layer just because no height source was available - the capture
        # and its defect detection still matter.
        logger.warning("No z height known for printer %s layer %s, recording 0", printer_id, layer_number)
        z_height = Decimal("0.00")

    async with db_session_factory() as db:
        job_id = await _running_job_id(db, printer_id)
        if job_id is None:
            logger.warning("Layer %s on printer %s with no running print job; skipping", layer_number, printer_id)
            return

        layer = Layer(job_id=job_id, layer_number=layer_number, z_height=z_height)
        db.add(layer)
        try:
            await db.commit()
        except IntegrityError:
            # Same layer seen twice (reconnect replay, retransmit) - the capture already exists.
            await db.rollback()
            logger.info("Layer %s for job %s already recorded, skipping", layer_number, job_id)
            return

    logger.info("Printer %s layer %s (z=%s) -> job %s, triggering capture", printer_id, layer_number, z_height, job_id)

    # Same channel and payload the manual trigger (scripts/mark_layers.py) publishes, so
    # capture/inference/frontend see no difference between an automatic and a manual layer.
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
