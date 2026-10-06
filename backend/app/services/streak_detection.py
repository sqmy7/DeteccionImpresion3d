from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Detection, Layer, LayerCapture


async def check_consecutive_streak(db: AsyncSession, job_id: int, camera_id: int, class_name: str, threshold: int) -> bool:
    """True exactly once: on the layer where a run of `threshold` consecutive layers (same
    job+camera, most recent first) all have `class_name` in their defect_classes - the moment
    the trend first crosses the threshold. False before that point, and false again on every
    later layer while the streak continues (checked by looking one layer further back: if that
    one also has the class, this same streak already fired). Shared by jam_detection.py
    (under_extrusion) and auto_pause.py (spaghetti) so the trend logic has one implementation."""
    stmt = (
        select(Detection.defect_classes)
        .join(LayerCapture, Detection.capture_id == LayerCapture.id)
        .join(Layer, LayerCapture.layer_id == Layer.id)
        .where(Layer.job_id == job_id, LayerCapture.camera_id == camera_id)
        .order_by(desc(Layer.layer_number))
        .limit(threshold + 1)
    )
    result = await db.execute(stmt)
    recent = [row[0] for row in result.all()]

    if len(recent) < threshold:
        return False

    streak = recent[:threshold]
    if not all(class_name in classes for classes in streak):
        return False

    if len(recent) > threshold and class_name in recent[threshold]:
        return False  # this streak already crossed the threshold on an earlier layer

    return True
