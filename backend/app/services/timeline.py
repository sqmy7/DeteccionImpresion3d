from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AlertStatus, Camera, CameraRole, Detection, Layer, LayerCapture, ModelVersion


class TimelineEntry:
    def __init__(
        self,
        layer_number: int,
        z_height: Decimal | None,
        capture_id: int | None,
        has_defect: bool,
        thumbnail_url: str | None,
        defect_classes: list[str] | None = None,
    ) -> None:
        self.layer_number = layer_number
        self.z_height = z_height
        self.capture_id = capture_id
        self.has_defect = has_defect
        self.thumbnail_url = thumbnail_url
        self.defect_classes = defect_classes or []


async def get_job_timeline(db: AsyncSession, job_id: int) -> list[TimelineEntry]:
    """One entry per layer, aggregated across every camera's capture/detection for it:
    has_defect is true if ANY camera flagged a defect and defect_classes is the union of the classes
    detected across cameras (so the UI can tell a layer flagged only by a low-confidence class apart
    from one with a reliable defect; the backend does not judge that, it just reports what was seen); the thumbnail/capture_id
    prefer the primary camera's capture (fall back to any other camera's) since that's what the
    dashboard's video feed already shows as "the" view of that printer."""
    stmt = (
        select(
            Layer.layer_number,
            Layer.z_height,
            LayerCapture.id,
            Camera.role,
            Detection.has_defect,
            Detection.defect_classes,
        )
        .select_from(Layer)
        .outerjoin(LayerCapture, LayerCapture.layer_id == Layer.id)
        .outerjoin(Camera, Camera.id == LayerCapture.camera_id)
        .outerjoin(Detection, Detection.capture_id == LayerCapture.id)
        .where(Layer.job_id == job_id)
        .order_by(Layer.layer_number)
    )
    rows = (await db.execute(stmt)).all()

    by_layer: dict[int, dict] = {}
    for layer_number, z_height, capture_id, camera_role, has_defect, defect_classes in rows:
        entry = by_layer.setdefault(
            layer_number,
            {"z_height": z_height, "has_defect": False, "defect_classes": set(), "capture_id": None, "capture_role": None},
        )
        if has_defect:
            entry["has_defect"] = True
        entry["defect_classes"].update(defect_classes or [])
        if capture_id is not None and (entry["capture_id"] is None or camera_role == CameraRole.primary):
            entry["capture_id"] = capture_id
            entry["capture_role"] = camera_role

    return [
        TimelineEntry(
            layer_number=layer_number,
            z_height=data["z_height"],
            capture_id=data["capture_id"],
            has_defect=data["has_defect"],
            defect_classes=sorted(data["defect_classes"]),
            thumbnail_url=f"/api/v1/layer-captures/{data['capture_id']}/thumbnail" if data["capture_id"] else None,
        )
        for layer_number, data in sorted(by_layer.items())
    ]


async def get_job_summary(db: AsyncSession, job_id: int) -> dict:
    """Dashboard-ready aggregate for a job, built on top of get_job_timeline rather than a second
    hand-rolled query - one source of truth for 'what counts as captured/defective per layer'.
    total_layers_recorded can exceed layers_captured if capture failed for some (camera busy, etc.) -
    a real, visible gap rather than silently treating a missing photo as a clean layer."""
    entries = await get_job_timeline(db, job_id)
    captured = [e for e in entries if e.capture_id is not None]
    with_defect = [e for e in captured if e.has_defect]

    defect_class_counts: dict[str, int] = {}
    for entry in captured:
        for class_name in entry.defect_classes:
            defect_class_counts[class_name] = defect_class_counts.get(class_name, 0) + 1

    active_alerts_count = await db.scalar(
        select(func.count(Alert.id))
        .select_from(Alert)
        .join(Detection, Detection.id == Alert.detection_id)
        .join(LayerCapture, LayerCapture.id == Detection.capture_id)
        .join(Layer, Layer.id == LayerCapture.layer_id)
        .where(Layer.job_id == job_id, Alert.status.in_([AlertStatus.new, AlertStatus.acknowledged]))
    )

    latest_model_version = await db.scalar(
        select(ModelVersion)
        .join(Detection, Detection.model_version_id == ModelVersion.id)
        .join(LayerCapture, LayerCapture.id == Detection.capture_id)
        .join(Layer, Layer.id == LayerCapture.layer_id)
        .where(Layer.job_id == job_id)
        .order_by(Detection.created_at.desc())
        .limit(1)
    )

    return {
        "job_id": job_id,
        "current_layer": entries[-1].layer_number if entries else None,
        "total_layers_recorded": len(entries),
        "layers_captured": len(captured),
        "layers_ok": len(captured) - len(with_defect),
        "layers_with_defect": len(with_defect),
        "defect_class_counts": defect_class_counts,
        "active_alerts_count": active_alerts_count or 0,
        "latest_model_version": (
            {"id": latest_model_version.id, "name": latest_model_version.name} if latest_model_version else None
        ),
    }
