from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import Detection, LayerCapture, ModelVersion
from app.db.session import get_db
from app.schemas.detection import DetectionCreate, DetectionRead

router = APIRouter(tags=["detections"], dependencies=[Depends(get_current_user)])


async def _get_capture_or_404(capture_id: int, db: AsyncSession) -> LayerCapture:
    capture = await db.get(LayerCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layer capture not found")
    return capture


async def _get_model_version_or_404(model_version_id: int, db: AsyncSession) -> ModelVersion:
    model_version = await db.get(ModelVersion, model_version_id)
    if model_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found")
    return model_version


@router.get("/layer-captures/{capture_id}/detections", response_model=list[DetectionRead])
async def list_detections(capture_id: int, db: AsyncSession = Depends(get_db)) -> list[Detection]:
    await _get_capture_or_404(capture_id, db)
    result = await db.execute(select(Detection).where(Detection.capture_id == capture_id).order_by(Detection.id))
    return list(result.scalars().all())


@router.post(
    "/layer-captures/{capture_id}/detections",
    response_model=DetectionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_detection(capture_id: int, payload: DetectionCreate, db: AsyncSession = Depends(get_db)) -> Detection:
    await _get_capture_or_404(capture_id, db)
    await _get_model_version_or_404(payload.model_version_id, db)

    detection = Detection(
        capture_id=capture_id,
        model_version_id=payload.model_version_id,
        has_defect=payload.has_defect,
        max_confidence=payload.max_confidence,
        defect_classes=payload.defect_classes,
        raw_output=payload.raw_output,
    )
    db.add(detection)
    await db.commit()
    await db.refresh(detection)
    return detection


@router.get("/detections/{detection_id}", response_model=DetectionRead)
async def get_detection(detection_id: int, db: AsyncSession = Depends(get_db)) -> Detection:
    detection = await db.get(Detection, detection_id)
    if detection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return detection
