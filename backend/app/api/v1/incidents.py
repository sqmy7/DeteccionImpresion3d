from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_current_user, require_admin
from app.db.models import Detection, Incident, Layer, LayerCapture, PrinterEvent, PrintJob, TelemetrySample, User
from app.db.session import get_db
from app.schemas.incident import BoxOnFrame, IncidentDetail, IncidentDetection, IncidentLabel, IncidentRead
from app.services import incidents, printer_events, telemetry

router = APIRouter(tags=["incidents"], dependencies=[Depends(get_current_user)])

_EVENT_WINDOW_BEFORE = timedelta(minutes=2)
_EVENT_LIMIT = 400


def boxes_on_frame(raw_output: dict) -> list[dict]:
    """The model's boxes (normalized to the region it saw) as fractions of the whole frame, the way the live
    view draws them. An older record without frame information is taken to be the whole frame."""
    frame = (raw_output or {}).get("frame") or {}
    roi = frame.get("roi") or {}
    full_w, full_h = frame.get("width"), frame.get("height")
    boxes = []
    for item in (raw_output or {}).get("detections", []):
        x1, y1, x2, y2 = item["box"]
        if full_w and full_h and roi:
            x1, x2 = (roi["x"] + x1 * roi["w"]) / full_w, (roi["x"] + x2 * roi["w"]) / full_w
            y1, y2 = (roi["y"] + y1 * roi["h"]) / full_h, (roi["y"] + y2 * roi["h"]) / full_h
        boxes.append(
            {"class_name": item["class"], "confidence": float(item["confidence"]),
             "x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4), "y2": round(y2, 4)}
        )
    return boxes


def _read(incident: Incident, job_file_name: str | None) -> IncidentRead:
    read = IncidentRead.model_validate(incident)
    seconds = None
    if incident.paused_at is not None and incident.first_defect_at is not None:
        seconds = round((incident.paused_at - incident.first_defect_at).total_seconds(), 1)
    return read.model_copy(update={"job_file_name": job_file_name, "seconds_to_pause": seconds})


async def _list(db: AsyncSession, *, printer_id: int | None, job_id: int | None, state: str, limit: int) -> list[IncidentRead]:
    query = select(Incident, PrintJob.file_name).join(PrintJob, PrintJob.id == Incident.print_job_id)
    if printer_id is not None:
        query = query.where(Incident.printer_id == printer_id)
    if job_id is not None:
        query = query.where(Incident.print_job_id == job_id)
    if state == "unclosed":
        query = query.where(Incident.status != "closed")
    elif state == "closed":
        query = query.where(Incident.status == "closed")
    rows = (await db.execute(query.order_by(Incident.id.desc()).limit(limit))).all()
    return [_read(incident, file_name) for incident, file_name in rows]


@router.get("/incidents", response_model=list[IncidentRead])
async def list_incidents(
    state: str = Query("all", pattern="^(all|unclosed|closed)$"),
    printer_id: int | None = None,
    job_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[IncidentRead]:
    return await _list(db, printer_id=printer_id, job_id=job_id, state=state, limit=limit)


@router.get("/printers/{printer_id}/incidents", response_model=list[IncidentRead])
async def list_printer_incidents(
    printer_id: int,
    state: str = Query("all", pattern="^(all|unclosed|closed)$"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[IncidentRead]:
    return await _list(db, printer_id=printer_id, job_id=None, state=state, limit=limit)


@router.get("/print-jobs/{job_id}/incidents", response_model=list[IncidentRead])
async def list_job_incidents(job_id: int, db: AsyncSession = Depends(get_db)) -> list[IncidentRead]:
    if await db.get(PrintJob, job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found")
    return await _list(db, printer_id=None, job_id=job_id, state="all", limit=200)


async def _get_or_404(incident_id: int, db: AsyncSession) -> Incident:
    incident = await db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: int, db: AsyncSession = Depends(get_db)) -> IncidentDetail:
    incident = await _get_or_404(incident_id, db)
    job = await db.get(PrintJob, incident.print_job_id)
    base = _read(incident, job.file_name if job else None)

    detection_ids = [item["detection_id"] for item in incident.streak or [] if item.get("detection_id")]
    rows = (
        await db.execute(
            select(Detection, LayerCapture, Layer)
            .join(LayerCapture, LayerCapture.id == Detection.capture_id)
            .join(Layer, Layer.id == LayerCapture.layer_id)
            .where(Detection.id.in_(detection_ids))
            .order_by(Layer.layer_number)
        )
    ).all() if detection_ids else []
    streak_by_detection = {item["detection_id"]: item for item in incident.streak or []}
    detections = [
        IncidentDetection(
            detection_id=detection.id,
            capture_id=capture.id,
            layer_number=layer.layer_number,
            z_height=float(layer.z_height) if layer.z_height is not None else None,
            captured_at=capture.captured_at,
            confidence=(streak_by_detection.get(detection.id) or {}).get("confidence"),
            image_url=f"/api/v1/layer-captures/{capture.id}/thumbnail",
            boxes=[BoxOnFrame(**box) for box in boxes_on_frame(detection.raw_output)],
        )
        for detection, capture, layer in rows
    ]

    window_start = (incident.first_defect_at or incident.opened_at) - _EVENT_WINDOW_BEFORE
    events = list(
        (
            await db.execute(
                select(PrinterEvent)
                .where(
                    PrinterEvent.printer_id == incident.printer_id,
                    PrinterEvent.print_job_id == incident.print_job_id,
                    PrinterEvent.ts >= window_start,
                )
                .order_by(PrinterEvent.id)
                .limit(_EVENT_LIMIT)
            )
        ).scalars()
    )
    chain = await printer_events.verify_chain(db, incident.printer_id)

    at_pause = None
    if incident.paused_at is not None:
        sample = (
            await db.execute(
                select(TelemetrySample)
                .where(TelemetrySample.print_job_id == incident.print_job_id)
                .order_by(func.abs(func.extract("epoch", TelemetrySample.ts - incident.paused_at)))
                .limit(1)
            )
        ).scalar_one_or_none()
        if sample is not None:
            at_pause = telemetry.clean_row({field: getattr(sample, field) for field in telemetry.SAMPLE_FIELDS})
            at_pause["ts"] = sample.ts.isoformat()
            at_pause["extra"] = sample.extra

    return IncidentDetail(
        **base.model_dump(),
        job={
            "id": job.id, "file_name": job.file_name, "status": job.status.value, "started_at": job.started_at,
            "ended_at": job.ended_at, "estimated_layers": job.estimated_layers,
        } if job else {},
        detections=detections,
        events=[printer_events.event_to_dict(event) for event in events],
        chain=chain,
        report_url=f"/api/v1/print-jobs/{incident.print_job_id}/report.pdf",
        telemetry_at_pause=at_pause,
    )


@router.post("/incidents/{incident_id}/label", response_model=IncidentRead)
async def label_incident(
    incident_id: int, payload: IncidentLabel, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> IncidentRead:
    incident = await _get_or_404(incident_id, db)
    await incidents.set_label(db, incident, payload.label, user.username)
    job = await db.get(PrintJob, incident.print_job_id)
    return _read(incident, job.file_name if job else None)


@router.post("/incidents/{incident_id}/dismiss", response_model=IncidentRead)
async def dismiss_incident(
    incident_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> IncidentRead:
    """«Ignorar»: the user looked at it and decided nothing needs doing. Does not touch the printer."""
    incident = await _get_or_404(incident_id, db)
    if incident.status == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This incident is already closed")
    # The service works with its own short sessions; they must go to the same database as this request.
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    await incidents.close_incidents(
        factory, incident_id=incident_id, outcome="ignored", decided_by=f"{user.username} (web)",
        detail={"how": "dismissed_by_user"},
    )
    await db.refresh(incident)
    job = await db.get(PrintJob, incident.print_job_id)
    return _read(incident, job.file_name if job else None)
