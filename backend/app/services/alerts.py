from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AlertStatus, Camera, Detection, LayerCapture, User
from app.schemas.alert import AlertCreate
from app.ws.manager import manager

# new -> acknowledged is the "someone is looking at this" step; acknowledged/new -> dismissed/false_positive
# are the terminal resolutions. Skipping straight from 'new' to a resolution is allowed too.
_ALLOWED_TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
    AlertStatus.new: {AlertStatus.acknowledged, AlertStatus.dismissed, AlertStatus.false_positive},
    AlertStatus.acknowledged: {AlertStatus.dismissed, AlertStatus.false_positive},
}


def _alert_event_payload(alert: Alert) -> dict:
    return {
        "alert_id": alert.id,
        "printer_id": alert.printer_id,
        "detection_id": alert.detection_id,
        "severity": alert.severity.value,
        "status": alert.status.value,
        "acknowledged_by": alert.acknowledged_by,
    }


async def create_alert(db: AsyncSession, detection_id: int, payload: AlertCreate) -> Alert:
    detection = await db.get(Detection, detection_id)
    if detection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")

    # printer_id is denormalized onto alerts; resolve it from the detection's capture/camera
    # rather than trusting the caller to pass a (possibly inconsistent) value.
    capture = await db.get(LayerCapture, detection.capture_id)
    camera = await db.get(Camera, capture.camera_id)

    alert = Alert(
        detection_id=detection_id,
        printer_id=camera.printer_id,
        severity=payload.severity,
        status=AlertStatus.new,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    await manager.broadcast("detection.alert", _alert_event_payload(alert))
    return alert


async def transition_alert_status(
    db: AsyncSession, alert: Alert, new_status: AlertStatus, current_user: User
) -> Alert:
    allowed = _ALLOWED_TRANSITIONS.get(alert.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition alert from '{alert.status.value}' to '{new_status.value}'",
        )

    alert.status = new_status
    if new_status == AlertStatus.acknowledged:
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(alert)
    await manager.broadcast("detection.alert", _alert_event_payload(alert))
    return alert
