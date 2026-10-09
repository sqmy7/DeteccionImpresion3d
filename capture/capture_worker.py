import asyncio
import base64
import json
import logging
import time

import cv2
from app.db.models import Camera, Layer, LayerCapture
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from capture.camera_sources.factory import get_camera_source
from capture.color_heuristic import detect_dominant_color_rgb
from capture.config import settings
from capture.live_stream import live_frames

logger = logging.getLogger(__name__)

_MAX_CAPTURE_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 0.5


async def handle_layer_ready(db_session_factory, redis_client, payload: dict) -> None:
    printer_id = payload["printer_id"]
    job_id = payload["job_id"]
    layer_number = payload["layer_number"]

    async with db_session_factory() as db:
        result = await db.execute(
            select(Camera).where(Camera.printer_id == printer_id, Camera.is_active.is_(True))
        )
        cameras = list(result.scalars().all())

        layer_row_id = await db.scalar(
            select(Layer.id).where(Layer.job_id == job_id, Layer.layer_number == layer_number)
        )

    if not cameras:
        logger.warning("No active cameras for printer %s; skipping layer %s capture", printer_id, layer_number)
        return

    if layer_row_id is None:
        logger.warning("No Layer row for job %s layer %s yet; skipping capture", job_id, layer_number)
        return

    await asyncio.gather(
        *(
            _capture_from_camera(db_session_factory, redis_client, printer_id, job_id, layer_number, layer_row_id, camera)
            for camera in cameras
        )
    )


def _read_frame_sync(camera: Camera):
    source = get_camera_source(camera)
    try:
        source.open()
        return source.read_frame()
    finally:
        source.close()


def _crop_to_roi(frame, roi: dict | None):
    if not roi:
        return frame
    x, y, w, h = int(roi["x"]), int(roi["y"]), int(roi["w"]), int(roi["h"])
    return frame[y : y + h, x : x + w]


async def _capture_from_camera(
    db_session_factory,
    redis_client,
    printer_id: int,
    job_id: int,
    layer_number: int,
    layer_row_id: int,
    camera: Camera,
) -> None:
    # The continuous live stream (live_stream.py) already keeps this camera open and reads it
    # several times a second - reuse its latest frame instead of opening a second, competing
    # handle to the same device. Only falls back to a direct open/read/close (the old behavior)
    # if the stream hasn't produced anything recent yet, e.g. right at process startup.
    if live_frames.signal_lost(camera.id):
        # No photo is better than a black one: the layer is recorded without a capture, a visible gap, and
        # the model is not asked to find defects in an image with nothing in it.
        logger.error(
            "Camera %s delivers only black frames: layer %s of job %s has no photo", camera.id, layer_number, job_id
        )
        return

    frame = live_frames.get_recent(camera.id)
    if frame is None:
        logger.info("No recent live-stream frame for camera %s, falling back to a direct read", camera.id)
        for attempt in range(1, _MAX_CAPTURE_ATTEMPTS + 1):
            try:
                frame = await asyncio.to_thread(_read_frame_sync, camera)
                break
            except Exception:
                logger.warning(
                    "Capture attempt %s/%s failed for camera %s (printer %s, layer %s)",
                    attempt,
                    _MAX_CAPTURE_ATTEMPTS,
                    camera.id,
                    printer_id,
                    layer_number,
                    exc_info=True,
                )
                if attempt < _MAX_CAPTURE_ATTEMPTS:
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)

    if frame is None:
        logger.error(
            "Giving up on camera %s (printer %s, layer %s) after %s attempts",
            camera.id,
            printer_id,
            layer_number,
            _MAX_CAPTURE_ATTEMPTS,
        )
        return

    # One filename per camera (role, not just layer number) - two cameras on the same
    # printer would otherwise overwrite each other's file for the same layer.
    relative_path = f"{printer_id}/{job_id}/layer_{layer_number}_{camera.role.value}.jpg"
    absolute_path = settings.storage_root / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(absolute_path), frame)

    # Cache the full (uncropped) frame for the MJPEG stream endpoint, so the backend can
    # serve "the last known frame" without needing a live camera feed of its own or disk
    # access. Base64 text, not raw bytes: reuses the SAME decode_responses=True redis
    # client already used for pub/sub elsewhere, instead of a second binary connection.
    # No TTL on purpose - a real print's layers can be minutes apart, so this should keep
    # showing the last real frame between captures, not expire and flicker to a placeholder.
    try:
        ok, encoded = cv2.imencode(".jpg", frame)
        if ok:
            await redis_client.mset(
                {
                    f"latest_frame:{camera.id}": base64.b64encode(encoded.tobytes()).decode("ascii"),
                    f"latest_frame_at:{camera.id}": str(time.time()),
                }
            )
    except Exception:
        logger.warning("Failed to cache latest frame for camera %s", camera.id, exc_info=True)

    # Color is enriched metadata, not a defect signal - runs unconditionally, and a
    # failure here (e.g. a degenerate ROI) must not stop the capture from being saved.
    try:
        dominant_color_rgb = detect_dominant_color_rgb(_crop_to_roi(frame, camera.roi))
    except Exception:
        logger.warning(
            "Color detection failed for camera %s (printer %s, layer %s)",
            camera.id,
            printer_id,
            layer_number,
            exc_info=True,
        )
        dominant_color_rgb = None

    # Stored RELATIVE to storage_root, not absolute: capture runs natively (Windows/WSL
    # paths) while the inference worker runs in its own Docker container (different
    # filesystem view) - only a path relative to a shared "storage/snapshots" convention
    # is meaningful to both. Each side resolves it against its own local storage_root.
    async with db_session_factory() as db:
        capture = LayerCapture(
            layer_id=layer_row_id,
            camera_id=camera.id,
            image_path=relative_path,
            dominant_color_rgb=dominant_color_rgb,
        )
        db.add(capture)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.info("Capture for layer %s / camera %s already exists, skipping", layer_row_id, camera.id)
            return
        await db.refresh(capture)

    # Redis Stream (consumer group, guaranteed delivery) for the inference worker to pick up -
    # separate from the events:* pub/sub below, which is only for the WS-connected frontend.
    await redis_client.xadd(
        "captures:pending",
        {
            "capture_id": str(capture.id),
            "printer_id": str(printer_id),
            "job_id": str(job_id),
            "layer_number": str(layer_number),
            "camera_id": str(camera.id),
            "image_path": relative_path,
        },
    )

    # capture is a separate OS process from the backend - it can't call the backend's
    # in-memory WS ConnectionManager directly, so it goes through the same events:*
    # Redis relay the backend's redis_listener already forwards over /api/v1/ws.
    await redis_client.publish(
        "events:layer_captured",
        json.dumps(
            {
                "capture_id": capture.id,
                "printer_id": printer_id,
                "job_id": job_id,
                "layer_id": layer_row_id,
                "layer_number": layer_number,
                "camera_id": camera.id,
                "image_path": relative_path,
            }
        ),
    )
