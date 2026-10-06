import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertSeverity
from app.schemas.alert import AlertCreate
from app.services.alerts import create_alert
from app.services.streak_detection import check_consecutive_streak

logger = logging.getLogger(__name__)

_CONSECUTIVE_THRESHOLD = 3


async def check_jam_trend(db: AsyncSession, job_id: int, camera_id: int, detection_id: int) -> None:
    """under_extrusion is reported per-detection by the model; a jam is recognized here as a
    TREND (>= 3 consecutive layers for the same job+camera), not a single detection - this is
    deliberately backend logic, not model logic (per architecture)."""
    if not await check_consecutive_streak(db, job_id, camera_id, "under_extrusion", _CONSECUTIVE_THRESHOLD):
        return

    logger.warning(
        "Jam trend detected (job_id=%s, camera_id=%s): escalating detection %s to a critical alert",
        job_id,
        camera_id,
        detection_id,
    )
    await create_alert(db, detection_id=detection_id, payload=AlertCreate(severity=AlertSeverity.critical))
