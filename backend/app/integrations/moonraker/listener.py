import asyncio
import contextlib
import functools
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import websockets
from fastapi import HTTPException
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.db.models import JobStatus, Layer, Printer, PrinterStatus, PrintJob, TelemetrySample
from app.integrations.moonraker import command_log
from app.integrations.moonraker.interventions import (
    DetectedChange,
    FieldChange,
    InterventionTracker,
    detect_changes,
    print_phase,
)
from app.schemas.print_job import PrintJobCreate
from app.services import telemetry
from app.services.print_jobs import create_print_job, transition_job_status
from app.services.printer_events import EventOrigin, record_event
from app.ws.manager import manager

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 10
_LIST_OBJECTS_ID = 1
_SUBSCRIBE_ID = 2
_SAMPLE_INTERVAL_SECONDS = 1.0
# One insert every ~10 s instead of one per sample.
_SAMPLES_PER_INSERT = 10
# A state change within this window after a PrintWatch order of the same kind is attributed to it.
_COMMAND_ATTRIBUTION_SECONDS = 60
# After any of these Moonraker has dropped this connection's subscription (Klippy restarted or
# stopped), so the listener reconnects to subscribe again.
_KLIPPY_RESET_NOTIFICATIONS = {"notify_klippy_disconnected", "notify_klippy_shutdown", "notify_klippy_ready"}

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

# The PrintWatch print-control order that would explain entering each state.
_STATE_TO_ACTION = {"paused": "pause", "cancelled": "cancel"}


class _SubscriptionLost(Exception):
    """Moonraker has no live subscription for this connection; reconnecting makes a new one."""


def _websocket_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/websocket", "", ""))


class _PrinterState:
    """Moonraker pushes only the fields that changed, so each notification is a patch over
    the snapshot from the subscribe response - a layer-change notification carries no z_pos.
    Merging them here is what makes 'the layer changed, and z is X' answerable. `status` keeps
    every subscribed object merged, for telemetry."""

    def __init__(self) -> None:
        self.state: str | None = None
        self.filename: str | None = None
        self.z_pos: Decimal | None = None
        self.layer: int | None = None
        self.layer_count: int | None = None
        self.layer_height: Decimal | None = None
        self.status: dict[str, dict] = {}
        self.eventtime: float | None = None  # Klipper's clock at the last update
        self.job_id: int | None = None  # the open print job, kept in step by _sync_job
        self.connected = False  # subscription answered; a later disconnect is worth logging
        self.saved_geometry: tuple[int, dict] | None = None  # (job id, geometry) last stored

    @property
    def message(self) -> str | None:
        return (self.status.get("print_stats") or {}).get("message") or None

    @property
    def file_position(self) -> int | None:
        value = (self.status.get("virtual_sdcard") or {}).get("file_position")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def progress(self) -> float | None:
        value = (self.status.get("virtual_sdcard") or {}).get("progress")
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def phase(self, state: str | None = None) -> str:
        return print_phase(state or self.state, self.layer, self.progress, self.job_id is not None)

    def merge(self, status: dict, eventtime: float | None = None) -> None:
        for name, values in status.items():
            if isinstance(values, dict):
                self.status.setdefault(name, {}).update(values)
        if isinstance(eventtime, (int, float)):
            self.eventtime = float(eventtime)

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
        state = _PrinterState()
        reason = "connection closed"
        try:
            await _listen_once(printer_id, db_session_factory, redis_client, state)
        except asyncio.CancelledError:
            raise
        except _SubscriptionLost as error:
            reason = str(error)
            logger.warning(
                "Moonraker listener for printer %s: %s; reconnecting in %ss", printer_id, error, _RECONNECT_DELAY_SECONDS
            )
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            logger.exception(
                "Moonraker listener for printer %s failed, retrying in %ss", printer_id, _RECONNECT_DELAY_SECONDS
            )
        if state.connected:
            await _record_event_safely(
                db_session_factory,
                printer_id,
                "monitor_disconnected",
                EventOrigin.MONITOR,
                job_id=state.job_id,
                before=state.state,
                detail={"reason": reason},
            )
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


async def _send_rpc(ws, method: str, params: dict, request_id: int) -> None:
    await ws.send(json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": request_id}))


async def _listen_once(printer_id: int, db_session_factory, redis_client, state: _PrinterState) -> None:
    async with db_session_factory() as db:
        printer = await db.get(Printer, printer_id)
        if printer is None:
            return
        base_url = printer.octoprint_url

    ws_url = _websocket_url(base_url)
    sampler: asyncio.Task | None = None
    tracker: InterventionTracker | None = None
    tracker_task: asyncio.Task | None = None

    async with websockets.connect(ws_url, max_size=None) as ws:
        # List the printer's objects first, to subscribe to the sensors and fans it actually has.
        await _send_rpc(ws, "printer.objects.list", {}, _LIST_OBJECTS_ID)
        logger.info("Moonraker listener for printer %s connected to %s", printer_id, ws_url)

        try:
            async for raw in ws:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if message.get("id") == _LIST_OBJECTS_ID:
                    objects = (message.get("result") or {}).get("objects")
                    if objects is None:
                        logger.warning(
                            "Printer %s did not list its objects (%s); subscribing to the core set",
                            printer_id,
                            message.get("error"),
                        )
                    subscription = telemetry.build_subscription(objects)
                    await _send_rpc(ws, "printer.objects.subscribe", {"objects": subscription}, _SUBSCRIBE_ID)
                    continue

                if message.get("id") == _SUBSCRIBE_ID:
                    if message.get("error"):
                        raise _SubscriptionLost(f"subscribe failed: {message['error']}")
                    result = message.get("result") or {}
                    state.merge(result.get("status", {}), result.get("eventtime"))
                    # Sync status and job, but not the layer: whatever layer was in progress when
                    # we connected has already been captured or never will be, and re-publishing
                    # it would duplicate work for a layer the nozzle has moved past. The job does
                    # need syncing here, so attaching to a print already running (backend restart
                    # mid-print) still records the remaining layers.
                    await _sync_printer_status(db_session_factory, printer_id, state)
                    await _sync_job(db_session_factory, printer_id, state)
                    await _sync_geometry(db_session_factory, printer_id, state)
                    state.connected = True
                    await _record_event_safely(
                        db_session_factory,
                        printer_id,
                        "monitor_connected",
                        EventOrigin.MONITOR,
                        job_id=state.job_id,
                        after=state.state,
                        detail={"file": state.filename, "layer": state.layer, "layer_count": state.layer_count},
                        klipper_eventtime=state.eventtime,
                    )
                    sampler = asyncio.create_task(_run_sampler(printer_id, base_url, db_session_factory, state))
                    tracker = InterventionTracker(
                        base_url, state, functools.partial(_record_event_safely, db_session_factory, printer_id)
                    )
                    tracker_task = asyncio.create_task(tracker.run())
                    if state.job_id is not None:
                        tracker.want_file(state.filename)
                    logger.info(
                        "Moonraker listener for printer %s baseline: state=%s layer=%s/%s z=%s",
                        printer_id,
                        state.state,
                        state.layer,
                        state.layer_count,
                        state.z_pos,
                    )
                    continue

                method = message.get("method")
                if method in _KLIPPY_RESET_NOTIFICATIONS:
                    await _record_event_safely(
                        db_session_factory,
                        printer_id,
                        method.removeprefix("notify_"),
                        EventOrigin.PRINTER,
                        job_id=state.job_id,
                    )
                    raise _SubscriptionLost(method)
                if method != "notify_status_update":
                    continue

                params = message.get("params") or [{}]
                patch = params[0] if params and isinstance(params[0], dict) else {}
                previous_state = state.state
                previous_layer = state.layer
                previous_phase = state.phase()
                position_before = state.file_position
                changes = detect_changes(state.status, patch)
                state.merge(patch, params[1] if len(params) > 1 else None)

                job_change: dict = {}
                if state.state != previous_state:
                    logger.info(
                        "Printer %s state: %s -> %s (file=%s)", printer_id, previous_state, state.state, state.filename
                    )
                    await _sync_printer_status(db_session_factory, printer_id, state)
                    job_change = await _sync_job(db_session_factory, printer_id, state)
                    if job_change.get("job_opened") and tracker is not None:
                        tracker.want_file(state.filename)
                await _sync_geometry(db_session_factory, printer_id, state)

                if changes and tracker is not None:
                    # Changes in the same update that closed a job (END_PRINT turning heaters off)
                    # still belong to that job.
                    job_id = job_change.get("job_closed") or state.job_id
                    phase = "end" if job_change.get("job_closed") else state.phase()
                    await _handle_field_changes(
                        db_session_factory, printer_id, state, tracker, changes, position_before, job_id, phase
                    )

                if state.state != previous_state:
                    await _record_state_change(
                        db_session_factory, printer_id, base_url, state, previous_state, previous_phase, job_change,
                        tracker, position_before,
                    )

                if state.layer != previous_layer and state.state == "printing":
                    await _handle_layer_change(db_session_factory, redis_client, printer_id, state)
        finally:
            if sampler is not None:
                sampler.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sampler
            if tracker_task is not None:
                tracker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await tracker_task
            if tracker is not None:
                await tracker.close()


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


async def _sync_job(db_session_factory, printer_id: int, state: _PrinterState) -> dict:
    """Opens a job when the printer starts printing and closes it when Klipper reports a
    terminal state, so a print needs no manual bookkeeping to show up in the timeline. Keeps
    state.job_id on the open job and returns what changed, for the event log."""
    async with db_session_factory() as db:
        job_id = await _running_job_id(db, printer_id)
        state.job_id = job_id

        if state.state == "printing":
            if job_id is not None:
                return {}
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
                return {}
            state.job_id = job.id
            logger.info("Opened print job %s for printer %s (%s)", job.id, printer_id, job.file_name)
            return {"job_opened": job.id}

        new_job_status = _STATE_TO_JOB_STATUS.get(state.state or "")
        if new_job_status is None or job_id is None:
            return {}

        job = await db.get(PrintJob, job_id)
        try:
            await transition_job_status(db, job, new_job_status)
        except HTTPException:
            logger.warning("Could not close print job %s for printer %s", job_id, printer_id, exc_info=True)
            return {}
        state.job_id = None
        logger.info("Closed print job %s for printer %s as %s", job_id, printer_id, new_job_status.value)
        return {"job_closed": job_id, "job_status": new_job_status.value}


async def _sync_geometry(db_session_factory, printer_id: int, state: _PrinterState) -> None:
    """Keeps the live bed geometry current and the open job's copy of it up to date (the objects
    arrive a moment after the print starts, when the file declares them)."""
    geometry = telemetry.geometry_from_status(state.status)
    telemetry.latest_geometry[printer_id] = geometry
    if state.job_id is None or state.saved_geometry == (state.job_id, geometry):
        return
    try:
        async with db_session_factory() as db:
            job = await db.get(PrintJob, state.job_id)
            if job is not None:
                job.geometry = geometry
                await db.commit()
        state.saved_geometry = (state.job_id, geometry)
    except Exception:
        logger.warning("Could not store the bed geometry of job %s", state.job_id, exc_info=True)


def _parse_klipper_message(message: str) -> dict:
    """The Creality firmware reports errors as a JSON string ({"code": "key243", "msg": ...});
    upstream Klipper as plain text."""
    try:
        parsed = json.loads(message)
    except (TypeError, ValueError):
        return {"message": message}
    return parsed if isinstance(parsed, dict) else {"message": message}


def _describe_command(command: command_log.SentCommand) -> dict:
    return {
        "action": command.action,
        # Only the auto-pause sends orders without naming who asked (see client.send_print_action).
        "source": "web" if command.requested_by else "auto_pause",
        "requested_by": command.requested_by,
        "sent_at": command.sent_at.isoformat(),
        "ok": command.ok,
        "error": command.error,
    }


async def _record_state_change(
    db_session_factory,
    printer_id: int,
    base_url: str,
    state: _PrinterState,
    previous_state: str | None,
    previous_phase: str,
    job_change: dict,
    tracker: InterventionTracker | None,
    position_before: int | None,
) -> None:
    """Logs a print-state change. PrintWatch's own orders and the printer's own end states are
    known at once; anything else goes to the tracker, which looks for the console command or file
    line behind it (or settles on "external")."""
    # Orders logged first, so the chain reads "PrintWatch asked to pause" before "paused".
    await _log_sent_commands(db_session_factory, printer_id, base_url, state)

    new_state = state.state
    origin: EventOrigin | None = None
    detail: dict = dict(job_change)
    job_id = job_change.get("job_opened") or job_change.get("job_closed") or state.job_id

    if previous_state == "paused" and new_state == "printing":
        action = "resume"
    else:
        action = _STATE_TO_ACTION.get(new_state or "")
    if action is not None:
        command = command_log.claim_recent(base_url, action, _COMMAND_ATTRIBUTION_SECONDS)
        if command is not None:
            origin = EventOrigin.PRINTWATCH
            detail["printwatch_order"] = _describe_command(command)
    if new_state in ("complete", "error"):
        origin = EventOrigin.PRINTER
    if new_state == "error" and state.message:
        detail["error"] = _parse_klipper_message(state.message)

    if origin is None and tracker is not None:
        tracker.add(
            DetectedChange(
                event_type="state_changed",
                field="print_stats.state",
                before=previous_state,
                after=new_state,
                observed_at=datetime.now(timezone.utc),
                observed_monotonic=time.monotonic(),
                klipper_eventtime=state.eventtime,
                filename=state.filename,
                file_position_before=position_before,
                file_position_after=state.file_position,
                phase=previous_phase,
                job_id=job_id,
                detail=detail,
            )
        )
        return

    await _record_event_safely(
        db_session_factory,
        printer_id,
        "state_changed",
        origin or EventOrigin.EXTERNAL,
        job_id=job_id,
        field="print_stats.state",
        before=previous_state,
        after=new_state,
        detail={**detail, "phase": previous_phase},
        klipper_eventtime=state.eventtime,
    )


async def _handle_field_changes(
    db_session_factory,
    printer_id: int,
    state: _PrinterState,
    tracker: InterventionTracker,
    changes: list[FieldChange],
    position_before: int | None,
    job_id: int | None,
    phase: str,
) -> None:
    now = datetime.now(timezone.utc)
    for change in changes:
        if not change.needs_attribution:
            await _record_event_safely(
                db_session_factory,
                printer_id,
                change.event_type,
                EventOrigin.PRINTER,
                job_id=job_id,
                field=change.field,
                before=change.before,
                after=change.after,
                detail={"phase": phase},
                klipper_eventtime=state.eventtime,
            )
            continue
        tracker.add(
            DetectedChange(
                event_type=change.event_type,
                field=change.field,
                before=change.before,
                after=change.after,
                observed_at=now,
                observed_monotonic=time.monotonic(),
                klipper_eventtime=state.eventtime,
                filename=state.filename,
                file_position_before=position_before,
                file_position_after=state.file_position,
                phase=phase,
                job_id=job_id,
            )
        )


async def _log_sent_commands(db_session_factory, printer_id: int, base_url: str, state: _PrinterState) -> None:
    for command in command_log.take_unlogged(base_url):
        await _record_event_safely(
            db_session_factory,
            printer_id,
            "printwatch_command",
            EventOrigin.PRINTWATCH,
            job_id=state.job_id,
            field=f"printer/print/{command.action}",
            detail=_describe_command(command),
            ts=command.sent_at,
        )


async def _record_event_safely(db_session_factory, printer_id: int, event_type: str, origin: EventOrigin, **kwargs) -> None:
    """The event log must never stop the listener: layers and captures matter more."""
    try:
        await record_event(db_session_factory, printer_id, event_type, origin, **kwargs)
    except Exception:
        logger.warning("Could not record '%s' event for printer %s", event_type, printer_id, exc_info=True)


async def _run_sampler(printer_id: int, base_url: str, db_session_factory, state: _PrinterState) -> None:
    """Once per second: publish the current readings to the web, store them while a print job is
    open, and log the print-control orders PrintWatch sent since the last tick. Klipper reports
    up to 4 times per second; one stored sample per second is what the charts need (a 2 h print
    is ~7,200 rows, see docs/PROGRESO_TELEMETRIA.md)."""
    pending: list[dict] = []
    try:
        while True:
            await asyncio.sleep(_SAMPLE_INTERVAL_SECONDS)
            now = datetime.now(timezone.utc)
            sample = telemetry.sample_from_status(state.status)
            recording = state.job_id is not None and state.state in ("printing", "paused")

            reading = {"printer_id": printer_id, "job_id": state.job_id, "state": state.state, "ts": now.isoformat(), **sample}
            telemetry.latest_readings[printer_id] = reading
            await manager.broadcast("telemetry.sample", reading)

            if recording:
                pending.append({"print_job_id": state.job_id, "ts": now, "klipper_eventtime": state.eventtime, **sample})
            if len(pending) >= _SAMPLES_PER_INSERT or (pending and not recording):
                await _insert_samples(db_session_factory, printer_id, pending)
                pending = []

            await _log_sent_commands(db_session_factory, printer_id, base_url, state)
    finally:
        if pending:
            await _insert_samples(db_session_factory, printer_id, pending)


async def _insert_samples(db_session_factory, printer_id: int, rows: list[dict]) -> None:
    try:
        async with db_session_factory() as db:
            await db.execute(insert(TelemetrySample), rows)
            await db.commit()
    except Exception:
        logger.warning("Could not store %s telemetry samples for printer %s", len(rows), printer_id, exc_info=True)


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

        layer = Layer(
            job_id=job_id,
            layer_number=layer_number,
            z_height=z_height,
            telemetry=telemetry.layer_snapshot(state.status),
        )
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
