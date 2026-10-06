from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_query, require_admin
from app.core.config import settings
from app.db.models import Camera, Layer, LayerCapture, PrintJob
from app.db.session import get_db
from app.schemas.layer import LayerCreate, LayerRead
from app.schemas.layer_capture import LayerCaptureCreate, LayerCaptureRead

router = APIRouter(tags=["layers"], dependencies=[Depends(get_current_user)])

# Separate router: an <img> tag showing a thumbnail can't send an Authorization header,
# same reasoning as the camera stream endpoint - query-param auth instead.
thumbnail_router = APIRouter(tags=["layers"])


async def _get_job_or_404(job_id: int, db: AsyncSession) -> PrintJob:
    job = await db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found")
    return job


async def _get_layer_or_404(layer_id: int, db: AsyncSession) -> Layer:
    layer = await db.get(Layer, layer_id)
    if layer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layer not found")
    return layer


async def _get_camera_or_404(camera_id: int, db: AsyncSession) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


@router.get("/print-jobs/{job_id}/layers", response_model=list[LayerRead])
async def list_layers(job_id: int, db: AsyncSession = Depends(get_db)) -> list[Layer]:
    await _get_job_or_404(job_id, db)
    result = await db.execute(select(Layer).where(Layer.job_id == job_id).order_by(Layer.layer_number))
    return list(result.scalars().all())


@router.post(
    "/print-jobs/{job_id}/layers",
    response_model=LayerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_layer(job_id: int, payload: LayerCreate, db: AsyncSession = Depends(get_db)) -> Layer:
    await _get_job_or_404(job_id, db)

    layer = Layer(job_id=job_id, layer_number=payload.layer_number, z_height=payload.z_height)
    db.add(layer)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Layer {payload.layer_number} already exists for this job",
        )
    await db.refresh(layer)
    return layer


@router.get("/layers/{layer_id}", response_model=LayerRead)
async def get_layer(layer_id: int, db: AsyncSession = Depends(get_db)) -> Layer:
    return await _get_layer_or_404(layer_id, db)


@router.get("/layers/{layer_id}/captures", response_model=list[LayerCaptureRead])
async def list_layer_captures(layer_id: int, db: AsyncSession = Depends(get_db)) -> list[LayerCapture]:
    await _get_layer_or_404(layer_id, db)
    result = await db.execute(select(LayerCapture).where(LayerCapture.layer_id == layer_id).order_by(LayerCapture.id))
    return list(result.scalars().all())


@router.post(
    "/layers/{layer_id}/captures",
    response_model=LayerCaptureRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_layer_capture(
    layer_id: int, payload: LayerCaptureCreate, db: AsyncSession = Depends(get_db)
) -> LayerCapture:
    await _get_layer_or_404(layer_id, db)
    await _get_camera_or_404(payload.camera_id, db)

    capture = LayerCapture(
        layer_id=layer_id,
        camera_id=payload.camera_id,
        image_path=payload.image_path,
        dominant_color_rgb=payload.dominant_color_rgb,
    )
    db.add(capture)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This camera already has a capture for this layer",
        )
    await db.refresh(capture)
    return capture


@router.get("/layer-captures/{capture_id}", response_model=LayerCaptureRead)
async def get_layer_capture(capture_id: int, db: AsyncSession = Depends(get_db)) -> LayerCapture:
    capture = await db.get(LayerCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layer capture not found")
    return capture


@thumbnail_router.get("/layer-captures/{capture_id}/thumbnail")
async def get_layer_capture_thumbnail(
    capture_id: int, db: AsyncSession = Depends(get_db), _user=Depends(get_current_user_query)
) -> FileResponse:
    capture = await db.get(LayerCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layer capture not found")

    # image_path is relative to storage_root (see capture/capture_worker.py) - resolved
    # against backend's own view of the shared storage/snapshots mount, same as the
    # inference worker does on its side.
    image_path = settings.storage_root / capture.image_path
    if not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found on disk")

    return FileResponse(image_path, media_type="image/jpeg")
