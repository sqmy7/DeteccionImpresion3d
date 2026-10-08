import asyncio
import base64
import io
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_query, require_admin
from app.db.models import Camera, Printer
from app.db.session import get_db
from app.schemas.camera import CameraCreate, CameraRead, CameraUpdate

router = APIRouter(tags=["cameras"], dependencies=[Depends(get_current_user)])

# Separate router: an <img> tag streaming this can't send an Authorization header,
# so this route authenticates via query-param token (get_current_user_query) instead
# of the router-level header-based dependency above.
stream_router = APIRouter(tags=["cameras"])

_STREAM_BOUNDARY = "frame"
# capture/live_stream.py now writes latest_frame:{camera_id} continuously (~6fps, see
# capture/config.py::live_stream_fps), not just once per layer - this has to poll at roughly
# that same rate or the transport would still cap the video at the old once-per-layer cadence
# regardless of how often capture publishes. Slightly faster than the write rate on purpose,
# so this endpoint is never the bottleneck; re-sending the same cached frame once in a while
# is harmless; a browser <img> just repaints an identical frame.
_STREAM_INTERVAL_SECONDS = 0.12
_STALE_FRAME_SECONDS = 15.0  # older than this the live view says "no signal"
_placeholder_jpeg_cache: bytes | None = None


def _placeholder_jpeg() -> bytes:
    global _placeholder_jpeg_cache
    if _placeholder_jpeg_cache is None:
        image = Image.new("RGB", (640, 480), color=(30, 41, 59))
        draw = ImageDraw.Draw(image)
        draw.text((20, 230), "Sin senal: el servicio de captura no esta enviando video", fill=(148, 163, 184))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        _placeholder_jpeg_cache = buffer.getvalue()
    return _placeholder_jpeg_cache


async def _get_printer_or_404(printer_id: int, db: AsyncSession) -> Printer:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    return printer


async def _get_camera_or_404(camera_id: int, db: AsyncSession) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


@router.get("/printers/{printer_id}/cameras", response_model=list[CameraRead])
async def list_cameras(printer_id: int, db: AsyncSession = Depends(get_db)) -> list[Camera]:
    await _get_printer_or_404(printer_id, db)
    result = await db.execute(select(Camera).where(Camera.printer_id == printer_id).order_by(Camera.id))
    return list(result.scalars().all())


@router.post(
    "/printers/{printer_id}/cameras",
    response_model=CameraRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_camera(printer_id: int, payload: CameraCreate, db: AsyncSession = Depends(get_db)) -> Camera:
    await _get_printer_or_404(printer_id, db)

    camera = Camera(printer_id=printer_id, **payload.model_dump())
    db.add(camera)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Printer already has a '{payload.role.value}' camera",
        )
    await db.refresh(camera)
    return camera


@router.get("/cameras/{camera_id}", response_model=CameraRead)
async def get_camera(camera_id: int, db: AsyncSession = Depends(get_db)) -> Camera:
    return await _get_camera_or_404(camera_id, db)


@router.patch("/cameras/{camera_id}", response_model=CameraRead, dependencies=[Depends(require_admin)])
async def update_camera(camera_id: int, payload: CameraUpdate, db: AsyncSession = Depends(get_db)) -> Camera:
    camera = await _get_camera_or_404(camera_id, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(camera, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Printer already has a camera with that role",
        )
    await db.refresh(camera)
    return camera


@router.delete("/cameras/{camera_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_camera(camera_id: int, db: AsyncSession = Depends(get_db)) -> None:
    camera = await _get_camera_or_404(camera_id, db)
    await db.delete(camera)
    await db.commit()


async def _mjpeg_frames(request: Request, camera_id: int) -> AsyncIterator[bytes]:
    redis_client = request.app.state.redis
    boundary = _STREAM_BOUNDARY.encode()

    while True:
        if await request.is_disconnected():
            break

        # capture/live_stream.py continuously overwrites this key (~6fps, independent of
        # layer changes/inference) as base64 text in Redis - no live camera feed needed on
        # this side, and it reuses the same decode_responses=True client used everywhere
        # else instead of a second binary connection.
        cached, taken_at = await redis_client.mget(f"latest_frame:{camera_id}", f"latest_frame_at:{camera_id}")
        # The frame outlives the capture process in Redis: measured on the real printer, hours-old
        # frames were shown as live. No timestamp (a capture that predates it): trust the frame.
        stale = taken_at is not None and time.time() - float(taken_at) > _STALE_FRAME_SECONDS
        jpeg_bytes = base64.b64decode(cached) if cached and not stale else _placeholder_jpeg()

        yield (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n\r\n" + jpeg_bytes + b"\r\n"
        )
        await asyncio.sleep(_STREAM_INTERVAL_SECONDS)


@stream_router.get("/cameras/{camera_id}/snapshot")
async def camera_snapshot(
    camera_id: int, request: Request, db: AsyncSession = Depends(get_db), _user=Depends(get_current_user_query)
) -> Response:
    """The latest frame as a still JPEG, e.g. to mark the bed corners on when calibrating. The
    frame stays in Redis after capture stops, so its age goes in X-Frame-Age-Seconds (absent when
    the capture process predates that timestamp)."""
    await _get_camera_or_404(camera_id, db)
    cached, taken_at = await request.app.state.redis.mget(f"latest_frame:{camera_id}", f"latest_frame_at:{camera_id}")
    if not cached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No frame yet: is the capture process running?")
    headers = {"Cache-Control": "no-store"}
    if taken_at:
        headers["X-Frame-Age-Seconds"] = f"{max(0.0, time.time() - float(taken_at)):.1f}"
    return Response(base64.b64decode(cached), media_type="image/jpeg", headers=headers)


@stream_router.get("/cameras/{camera_id}/stream")
async def stream_camera(
    camera_id: int, request: Request, db: AsyncSession = Depends(get_db), _user=Depends(get_current_user_query)
) -> StreamingResponse:
    await _get_camera_or_404(camera_id, db)
    return StreamingResponse(
        _mjpeg_frames(request, camera_id),
        media_type=f"multipart/x-mixed-replace; boundary={_STREAM_BOUNDARY}",
    )
