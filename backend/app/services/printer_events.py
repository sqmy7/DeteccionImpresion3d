"""Event log (bitácora) of each printer: state changes and interventions, each with its origin.

Every event is chained to the previous event of the same printer by a SHA-256 hash over its own
content plus the previous hash, so editing or deleting a stored event afterwards breaks the chain
from that point on; verify_chain says where. What the chain alone cannot catch: deleting the
latest events, or someone with write access to the database recomputing every hash after the
edit. Keeping a copy of the latest hash outside the database (the job report prints it) closes
that gap."""

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import select, text

from app.db.models import PrinterEvent
from app.ws.manager import manager

# pg_advisory_xact_lock(namespace, printer_id) serializes appends to one printer's chain across
# every process and task that writes events, so two events never claim the same previous hash.
_LOCK_NAMESPACE = 7301


class EventOrigin(StrEnum):
    PRINTWATCH = "printwatch"  # an order PrintWatch sent: the auto-pause or the web's buttons
    CONSOLE = "console"  # a command found in Moonraker's console log (Fluidd/Mainsail console, API)
    GCODE_FILE = "gcode_file"  # programmed in the G-code file being printed
    PRINTER = "printer"  # the printer itself: Klipper errors, end of file, sensors
    EXTERNAL = "external"  # not PrintWatch, but which source (screen, Fluidd button, other app) is unknown
    MONITOR = "monitor"  # PrintWatch's own connection to the printer


def _jsonable(value):
    """Plain JSON types only (tuples become lists, anything exotic a string), exactly as the
    JSONB column will store them."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def _canonical(value):
    """Values as Postgres hands them back: JSONB may return a float such as 1e20 as an integer,
    so every number is hashed as a float."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return str(value)


def event_payload(event: PrinterEvent) -> dict:
    return {
        "printer_id": event.printer_id,
        "print_job_id": event.print_job_id,
        "ts": event.ts.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        "klipper_eventtime": event.klipper_eventtime,
        "event_type": event.event_type,
        "field": event.field,
        "value_before": event.value_before,
        "value_after": event.value_after,
        "origin": event.origin,
        "detail": event.detail,
    }


def event_hash(prev_hash: str | None, payload: dict) -> str:
    body = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{prev_hash or ''}|{body}".encode("utf-8")).hexdigest()


def event_to_dict(event: PrinterEvent) -> dict:
    return {
        "id": event.id,
        "printer_id": event.printer_id,
        "print_job_id": event.print_job_id,
        "ts": event.ts.isoformat(),
        "klipper_eventtime": event.klipper_eventtime,
        "event_type": event.event_type,
        "field": event.field,
        "value_before": event.value_before,
        "value_after": event.value_after,
        "origin": event.origin,
        "detail": event.detail,
        "hash": event.hash,
    }


async def record_event(
    db_session_factory,
    printer_id: int,
    event_type: str,
    origin: EventOrigin,
    *,
    job_id: int | None = None,
    field: str | None = None,
    before=None,
    after=None,
    detail: dict | None = None,
    klipper_eventtime: float | None = None,
    ts: datetime | None = None,
) -> PrinterEvent:
    """Appends one event to the printer's chain and pushes it to the web clients."""
    event = PrinterEvent(
        printer_id=printer_id,
        print_job_id=job_id,
        ts=ts or datetime.now(timezone.utc),
        klipper_eventtime=klipper_eventtime,
        event_type=event_type,
        field=field,
        value_before=_jsonable(before),
        value_after=_jsonable(after),
        origin=str(origin),
        detail=_jsonable(detail),
    )
    async with db_session_factory() as db:
        async with db.begin():
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :printer_id)"),
                {"namespace": _LOCK_NAMESPACE, "printer_id": printer_id},
            )
            event.prev_hash = await db.scalar(
                select(PrinterEvent.hash)
                .where(PrinterEvent.printer_id == printer_id)
                .order_by(PrinterEvent.id.desc())
                .limit(1)
            )
            event.hash = event_hash(event.prev_hash, event_payload(event))
            db.add(event)

    await manager.broadcast("printer.event", event_to_dict(event))
    return event


async def list_events(
    db, printer_id: int, *, job_id: int | None = None, before_id: int | None = None, limit: int = 100
) -> list[PrinterEvent]:
    """Newest first; before_id pages backwards."""
    query = select(PrinterEvent).where(PrinterEvent.printer_id == printer_id)
    if job_id is not None:
        query = query.where(PrinterEvent.print_job_id == job_id)
    if before_id is not None:
        query = query.where(PrinterEvent.id < before_id)
    result = await db.execute(query.order_by(PrinterEvent.id.desc()).limit(limit))
    return list(result.scalars().all())


async def verify_chain(db, printer_id: int) -> dict:
    """Recomputes the printer's chain from the first event. reason is "prev_hash_mismatch" (an
    event before this one was deleted, inserted or reordered) or "content_changed" (this event
    was edited after it was recorded)."""
    result = await db.execute(
        select(PrinterEvent).where(PrinterEvent.printer_id == printer_id).order_by(PrinterEvent.id)
    )
    previous = None
    checked = 0
    for event in result.scalars():
        checked += 1
        reason = None
        if event.prev_hash != previous:
            reason = "prev_hash_mismatch"
        elif event_hash(previous, event_payload(event)) != event.hash:
            reason = "content_changed"
        if reason is not None:
            return {"ok": False, "events_checked": checked, "first_broken_id": event.id, "reason": reason, "last_hash": None}
        previous = event.hash
    return {"ok": True, "events_checked": checked, "first_broken_id": None, "reason": None, "last_hash": previous}
