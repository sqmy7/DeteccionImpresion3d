"""Incidents: one record per thing that called for a decision during a print.

An incident opens when (docs/META_FINAL.md, decisions of 2026-10-09):
  - the spaghetti streak is reached: "would_pause" in warn mode, "auto_pause" (the countdown) in on mode;
  - the print is paused, by anyone ("pause");
  - a detection of an eligible class reaches the threshold ("detection": INCIDENT_CLASSES at or above
    INCIDENT_MIN_CONFIDENCE; one incident per job and class at most, ever);
  - the countdown is aborted with no incident open (the abort closes it as "ignored").
Only one incident per job and class stays unclosed (a partial unique index in the database), so every
path here is idempotent: a second trigger for the same job and class is added to the open incident.

Nothing in this module sends anything to a printer. Failures here must never break the code that calls it:
callers wrap these in try/except and log."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.models import Detection, Incident, Layer, LayerCapture, PrintJob, TelemetrySample
from app.services import eta, telemetry
from app.ws.manager import manager

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("open", "paused", "unconfirmed")
PAUSE_CLASS = "pausa"  # the class of a pause that has no detection behind it
MAX_STREAK = 10
OUTCOMES = ("resumed", "cancelled", "ignored", "error")
LABELS = ("unlabeled", "correct", "false_positive")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).isoformat() if moment else None


def _parse(moment: str | None) -> datetime | None:
    return datetime.fromisoformat(moment) if moment else None


def current_mode() -> str | None:
    mode = settings.auto_pause_mode
    return mode if mode in ("on", "warn") else None


def summary(incident: Incident) -> dict:
    """What the web needs to show that an incident exists (the WebSocket payload)."""
    return {
        "incident_id": incident.id,
        "printer_id": incident.printer_id,
        "job_id": incident.print_job_id,
        "reason": incident.reason,
        "mode": incident.mode,
        "defect_class": incident.defect_class,
        "status": incident.status,
        "outcome": incident.outcome,
        "opened_at": _iso(incident.opened_at),
    }


async def streak_items(db, job_id: int, camera_id: int, limit: int = 3) -> list[dict]:
    """The latest `limit` photos of the job that have a detection, oldest first, with what the incident keeps
    of each: layer, detection, capture, the model's confidence and when the photo was taken."""
    rows = await db.execute(
        select(Layer.layer_number, Detection.id, Detection.max_confidence, LayerCapture.id, LayerCapture.captured_at)
        .join(LayerCapture, LayerCapture.layer_id == Layer.id)
        .join(Detection, Detection.capture_id == LayerCapture.id)
        .where(Layer.job_id == job_id, LayerCapture.camera_id == camera_id)
        .order_by(Layer.layer_number.desc())
        .limit(limit)
    )
    items = [
        {
            "layer": number,
            "detection_id": detection_id,
            "capture_id": capture_id,
            "confidence": None if confidence is None else float(confidence),
            "captured_at": _iso(captured_at),
        }
        for number, detection_id, confidence, capture_id, captured_at in rows.all()
    ]
    return list(reversed(items))


async def build_snapshot(db, job: PrintJob, layer_number: int | None) -> dict:
    """The printer as it was when the incident opened: the job's latest telemetry sample, the telemetry row of
    the layer, and the time printed and left by the slicer's estimate (the printer's own print clock)."""
    sample = (
        await db.execute(
            select(TelemetrySample).where(TelemetrySample.print_job_id == job.id).order_by(TelemetrySample.ts.desc()).limit(1)
        )
    ).scalar_one_or_none()
    sample_row = None
    printed_s = None
    if sample is not None:
        sample_row = telemetry.clean_row({field: getattr(sample, field) for field in telemetry.SAMPLE_FIELDS})
        sample_row["ts"] = _iso(sample.ts)
        sample_row["extra"] = sample.extra
        raw = (sample.extra or {}).get("print_stats.print_duration")
        printed_s = float(raw) if isinstance(raw, (int, float)) else None

    layer_query = select(Layer).where(Layer.job_id == job.id)
    layer_query = (
        layer_query.where(Layer.layer_number == layer_number) if layer_number is not None else layer_query.order_by(Layer.layer_number.desc())
    )
    layer = (await db.execute(layer_query.limit(1))).scalar_one_or_none()

    estimated_total = (telemetry.job_file_info(job.geometry, job.file_name) or {}).get("estimated_time")
    return {
        "taken_at": _iso(_now()),
        "sample": sample_row,
        "layer": None if layer is None else {"layer_number": layer.layer_number, "z_height": float(layer.z_height), "telemetry": layer.telemetry},
        "printed_s": printed_s,
        "estimated_total_s": estimated_total,
        "remaining_s": eta.by_slicer(estimated_total, printed_s),
    }


def _merge_streak(old: list, new: list) -> list:
    by_layer = {item["layer"]: item for item in (*old, *new)}
    return [by_layer[layer] for layer in sorted(by_layer)][-MAX_STREAK:]


def _add_trigger(incident: Incident, reason: str, at: datetime, **extra) -> None:
    detail = dict(incident.detail or {})
    triggers = list(detail.get("triggers") or [])
    if all(trigger.get("reason") != reason for trigger in triggers):
        triggers.append({"reason": reason, "at": _iso(at), **extra})
    detail["triggers"] = triggers
    incident.detail = detail


def _attach(incident: Incident, *, reason: str, streak: list | None, detection_id: int | None, announced: bool, mode: str | None, now: datetime) -> None:
    """Adds a new trigger to an incident that is already open."""
    if streak:
        incident.streak = _merge_streak(list(incident.streak or []), streak)
        firsts = [moment for moment in (_parse(item.get("captured_at")) for item in incident.streak) if moment]
        if firsts:
            incident.first_defect_at = min([*firsts, *([incident.first_defect_at] if incident.first_defect_at else [])])
    if detection_id is not None:
        incident.detection_id = detection_id
    if announced and incident.announced_at is None:
        incident.announced_at = now
    if mode and incident.mode is None:
        incident.mode = mode
    _add_trigger(incident, reason, now)


async def open_incident(
    db_session_factory,
    *,
    job_id: int,
    printer_id: int,
    defect_class: str,
    reason: str,
    camera_id: int | None = None,
    streak: list | None = None,
    detection_id: int | None = None,
    announced: bool = False,
    detail: dict | None = None,
) -> tuple[int, bool]:
    """Opens the incident of this job and class, or adds the trigger to the one already open. Returns its id
    and whether it was just created."""
    now = _now()
    mode = current_mode()
    async with db_session_factory() as db:
        job = await db.get(PrintJob, job_id)
        if job is None:
            raise ValueError(f"job {job_id} does not exist")
        layer_number = streak[-1]["layer"] if streak else None
        firsts = [moment for moment in (_parse(item.get("captured_at")) for item in streak or []) if moment]
        values = {
            "print_job_id": job_id,
            "printer_id": printer_id,
            "camera_id": camera_id,
            "reason": reason,
            "mode": mode,
            "defect_class": defect_class,
            "streak": streak or [],
            "detection_id": detection_id,
            "first_defect_at": min(firsts) if firsts else None,
            "announced_at": now if announced else None,
            "status": "open",
            "telemetry_snapshot": await build_snapshot(db, job, layer_number),
            "detail": {"triggers": [{"reason": reason, "at": _iso(now)}], **(detail or {})},
        }
        statement = (
            pg_insert(Incident)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["print_job_id", "defect_class"], index_where=text("status <> 'closed'"))
            .returning(Incident.id)
        )
        new_id = (await db.execute(statement)).scalar_one_or_none()
        created = new_id is not None
        if created:
            incident = await db.get(Incident, new_id)
        else:
            incident = (
                await db.execute(
                    select(Incident).where(
                        Incident.print_job_id == job_id, Incident.defect_class == defect_class, Incident.status != "closed"
                    )
                )
            ).scalar_one()
            _attach(incident, reason=reason, streak=streak, detection_id=detection_id, announced=announced, mode=mode, now=now)
        await db.commit()
        await db.refresh(incident)
        payload = summary(incident)
    await manager.broadcast("incident.opened" if created else "incident.updated", payload)
    return payload["incident_id"], created


async def _unclosed(db, *, incident_id: int | None, job_id: int | None) -> list[Incident]:
    query = select(Incident).where(Incident.status != "closed")
    if incident_id is not None:
        query = query.where(Incident.id == incident_id)
    elif job_id is not None:
        query = query.where(Incident.print_job_id == job_id)
    else:
        return []
    return list((await db.execute(query.order_by(Incident.id))).scalars().all())


async def _update(db_session_factory, *, incident_id: int | None = None, job_id: int | None = None, change) -> list[dict]:
    """Applies `change(incident, now)` to the unclosed incidents found by id or by job, and broadcasts them."""
    now = _now()
    async with db_session_factory() as db:
        incidents = await _unclosed(db, incident_id=incident_id, job_id=job_id)
        for incident in incidents:
            change(incident, now)
        await db.commit()
        payloads = []
        for incident in incidents:
            await db.refresh(incident)
            payloads.append(summary(incident))
    for payload in payloads:
        await manager.broadcast("incident.updated", payload)
    return payloads


async def mark_pause_sent(db_session_factory, incident_id: int, at: datetime | None = None) -> None:
    def change(incident: Incident, now: datetime) -> None:
        incident.pause_sent_at = at or now

    await _update(db_session_factory, incident_id=incident_id, change=change)


async def mark_paused(db_session_factory, *, incident_id: int | None = None, job_id: int | None = None, origin: str | None = None, order: dict | None = None) -> None:
    """Klipper is paused. The first confirmation wins (the web's check and the listener can both report it)."""

    def change(incident: Incident, now: datetime) -> None:
        if incident.paused_at is None:
            incident.paused_at = now
        incident.status = "paused"
        detail = dict(incident.detail or {})
        detail.setdefault("pause_origin", origin or "unknown")
        if order:
            detail.setdefault("pause_order", order)
        incident.detail = detail

    await _update(db_session_factory, incident_id=incident_id, job_id=job_id, change=change)


async def mark_unconfirmed(db_session_factory, incident_id: int, **detail) -> None:
    def change(incident: Incident, now: datetime) -> None:
        if incident.status == "open":
            incident.status = "unconfirmed"
        merged = dict(incident.detail or {})
        merged["unconfirmed"] = {"at": _iso(now), **detail}
        incident.detail = merged

    await _update(db_session_factory, incident_id=incident_id, change=change)


async def close_incidents(
    db_session_factory,
    *,
    incident_id: int | None = None,
    job_id: int | None = None,
    outcome: str,
    decided_by: str | None,
    detail: dict | None = None,
) -> list[dict]:
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}")

    def change(incident: Incident, now: datetime) -> None:
        incident.status = "closed"
        incident.outcome = outcome
        incident.decided_by = decided_by
        incident.decided_at = now
        if detail:
            merged = dict(incident.detail or {})
            merged["closing"] = detail
            incident.detail = merged

    return await _update(db_session_factory, incident_id=incident_id, job_id=job_id, change=change)


async def set_label(db, incident: Incident, label: str, username: str) -> Incident:
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}")
    incident.label = label
    incident.labeled_by = None if label == "unlabeled" else username
    incident.labeled_at = None if label == "unlabeled" else _now()
    await db.commit()
    await db.refresh(incident)
    await manager.broadcast("incident.updated", summary(incident))
    return incident


# ---------------------------------------------------------------- detections and printer states

async def record_detection(db_session_factory, payload: dict) -> int | None:
    """A detection result arrived: open (or extend) the incident of every eligible class it contains."""
    if not payload.get("has_defect"):
        return None
    eligible_classes = settings.incident_class_list
    async with db_session_factory() as db:
        detection = await db.get(Detection, payload["detection_id"])
        if detection is None:
            return None
        confidence: dict[str, float] = {}
        for item in (detection.raw_output or {}).get("detections", []):
            confidence[item["class"]] = max(confidence.get(item["class"], 0.0), float(item["confidence"]))
        eligible = {name: value for name, value in confidence.items() if name in eligible_classes and value >= settings.incident_min_confidence}
        if not eligible:
            return None
        capture = await db.get(LayerCapture, detection.capture_id)
        layer = await db.get(Layer, capture.layer_id)
        job_id = layer.job_id
        known = {
            (incident.defect_class, incident.status != "closed")
            for incident in (await db.execute(select(Incident).where(Incident.print_job_id == job_id))).scalars()
        }
        item = {
            "layer": layer.layer_number,
            "detection_id": detection.id,
            "capture_id": capture.id,
            "captured_at": _iso(capture.captured_at),
        }
    last_id = None
    for name, value in eligible.items():
        if (name, False) in known and (name, True) not in known:
            continue  # a closed incident of this class exists: a lone detection does not open another one
        last_id, _ = await open_incident(
            db_session_factory,
            job_id=job_id,
            printer_id=payload["printer_id"],
            camera_id=payload.get("camera_id"),
            defect_class=name,
            reason="detection",
            streak=[{**item, "confidence": value}],
            detection_id=detection.id,
        )
    return last_id


def _who(origin: str | None, order: dict | None) -> str:
    if order and order.get("requested_by"):
        return str(order["requested_by"])
    if order:
        return "pausa automática"
    return {"console": "consola de Klipper", "external": "pantalla o Fluidd (externo)", "printer": "la impresora", "gcode_file": "archivo G-code"}.get(origin or "", "desconocido")


async def on_state_change(
    db_session_factory,
    *,
    printer_id: int,
    job_id: int | None,
    previous_state: str | None,
    new_state: str | None,
    origin: str | None,
    order: dict | None,
) -> None:
    """The printer changed print state: a pause opens or confirms an incident, and a resume, a cancel, an error
    or the end of the job closes the open ones. `origin` is None when the logbook has not attributed it yet."""
    if job_id is None:
        return
    if new_state == "paused":
        await _register_pause(db_session_factory, printer_id, job_id, origin, order)
    elif previous_state == "paused" and new_state == "printing":
        await close_incidents(db_session_factory, job_id=job_id, outcome="resumed", decided_by=_who(origin, order))
    elif new_state == "cancelled":
        await close_incidents(db_session_factory, job_id=job_id, outcome="cancelled", decided_by=_who(origin, order))
    elif new_state == "error":
        await close_incidents(db_session_factory, job_id=job_id, outcome="error", decided_by="la impresora")
    elif new_state == "complete":
        await close_incidents(db_session_factory, job_id=job_id, outcome="ignored", decided_by=None, detail={"reason": "job_ended"})


async def _register_pause(db_session_factory, printer_id: int, job_id: int, origin: str | None, order: dict | None) -> None:
    async with db_session_factory() as db:
        unclosed = await _unclosed(db, incident_id=None, job_id=job_id)
    if unclosed:
        await mark_paused(db_session_factory, job_id=job_id, origin=origin, order=order)
        return
    incident_id, _ = await open_incident(
        db_session_factory,
        job_id=job_id,
        printer_id=printer_id,
        defect_class=PAUSE_CLASS,
        reason="pause",
        detail={"pause_origin": origin or "unknown"},
    )
    await mark_paused(db_session_factory, incident_id=incident_id, origin=origin, order=order)
