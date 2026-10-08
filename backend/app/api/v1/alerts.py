from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import Alert, AlertStatus, Detection, Layer, LayerCapture, Printer, PrintJob, User
from app.db.session import get_db
from app.schemas.alert import AlertCreate, AlertListItem, AlertRead, AlertTransition
from app.services.alerts import create_alert, transition_alert_status

router = APIRouter(tags=["alerts"], dependencies=[Depends(get_current_user)])


async def _get_detection_or_404(detection_id: int, db: AsyncSession) -> Detection:
    detection = await db.get(Detection, detection_id)
    if detection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return detection


async def _get_alert_or_404(alert_id: int, db: AsyncSession) -> Alert:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.get("/alerts", response_model=list[AlertListItem])
async def list_alerts(
    status_filter: AlertStatus | None = Query(default=None, alias="status"),
    job_id: int | None = Query(default=None, description="Scope to alerts raised on this print job's layers"),
    db: AsyncSession = Depends(get_db),
) -> list[AlertListItem]:
    # printer_name, the job and the layer joined in here rather than left to the frontend - avoids
    # an N+1 of lookups for what's meant to be a single at-a-glance list. Alert has no job_id
    # column: the job is only reachable through its detection's capture's layer.
    stmt = (
        select(Alert, Printer.name, Layer.job_id, Layer.layer_number, PrintJob.file_name)
        .join(Printer, Printer.id == Alert.printer_id)
        .outerjoin(Detection, Detection.id == Alert.detection_id)
        .outerjoin(LayerCapture, LayerCapture.id == Detection.capture_id)
        .outerjoin(Layer, Layer.id == LayerCapture.layer_id)
        .outerjoin(PrintJob, PrintJob.id == Layer.job_id)
    )
    if job_id is not None:
        stmt = stmt.where(Layer.job_id == job_id)
    stmt = stmt.order_by(Alert.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Alert.status == status_filter)

    rows = (await db.execute(stmt)).all()
    return [
        AlertListItem(
            id=alert.id,
            detection_id=alert.detection_id,
            printer_id=alert.printer_id,
            printer_name=printer_name,
            severity=alert.severity,
            status=alert.status,
            acknowledged_by=alert.acknowledged_by,
            acknowledged_at=alert.acknowledged_at,
            created_at=alert.created_at,
            print_job_id=print_job_id,
            layer_number=layer_number,
            file_name=file_name,
        )
        for alert, printer_name, print_job_id, layer_number, file_name in rows
    ]


@router.get("/detections/{detection_id}/alerts", response_model=list[AlertRead])
async def list_alerts_for_detection(detection_id: int, db: AsyncSession = Depends(get_db)) -> list[Alert]:
    await _get_detection_or_404(detection_id, db)
    result = await db.execute(select(Alert).where(Alert.detection_id == detection_id).order_by(Alert.id))
    return list(result.scalars().all())


@router.post(
    "/detections/{detection_id}/alerts",
    response_model=AlertRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_alert_endpoint(detection_id: int, payload: AlertCreate, db: AsyncSession = Depends(get_db)) -> Alert:
    return await create_alert(db, detection_id, payload)


@router.get("/alerts/{alert_id}", response_model=AlertRead)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> Alert:
    return await _get_alert_or_404(alert_id, db)


@router.post("/alerts/{alert_id}/transition", response_model=AlertRead, dependencies=[Depends(require_admin)])
async def transition_alert(
    alert_id: int,
    payload: AlertTransition,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Alert:
    alert = await _get_alert_or_404(alert_id, db)
    return await transition_alert_status(db, alert, payload.status, current_user)
