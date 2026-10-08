import asyncio
import base64
import logging
import time

import cv2
import numpy as np
import redis.asyncio as redis
from app.db.models import Camera

from capture.camera_sources.factory import get_camera_source
from capture.config import settings

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 5
_STALE_SECONDS = 3.0  # older than this -> treated as "no live frame available" by callers


class LiveFrameStore:
    """In-process cache of the most recent frame per camera, written by run_live_stream below
    and read by capture_worker.py's per-layer capture - so layer changes don't need their own
    open()/read()/close() on a device the continuous loop already keeps open. A plain dict is
    safe to share across coroutines here: everything runs in one asyncio event loop in this
    process, and a dict item assignment can't be observed half-written."""

    def __init__(self) -> None:
        self._frames: dict[int, tuple[np.ndarray, float]] = {}

    def set(self, camera_id: int, frame: np.ndarray) -> None:
        self._frames[camera_id] = (frame, time.monotonic())

    def get_recent(self, camera_id: int, max_age: float = _STALE_SECONDS) -> np.ndarray | None:
        entry = self._frames.get(camera_id)
        if entry is None:
            return None
        frame, seen_at = entry
        return frame if (time.monotonic() - seen_at) <= max_age else None


live_frames = LiveFrameStore()


async def run_live_stream(camera: Camera) -> None:
    """Keeps camera's device open for the process lifetime and continuously publishes frames -
    to live_frames (for the per-layer capture path) and to Redis (for the MJPEG endpoint) - at
    a fixed, modest rate, entirely independent of layer_ready events and inference (still once
    per layer, unchanged). Reconnects on its own if the device or Redis hiccups."""
    while True:
        try:
            await _stream_once(camera)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Live stream for camera %s (%s) failed, reopening in %ss",
                camera.id, camera.name, _RECONNECT_DELAY_SECONDS,
            )
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


async def _stream_once(camera: Camera) -> None:
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    source = get_camera_source(camera)
    await asyncio.to_thread(source.open)
    logger.info("Live stream for camera %s (%s) started at ~%.1f fps", camera.id, camera.name, settings.live_stream_fps)

    try:
        interval = 1.0 / settings.live_stream_fps
        while True:
            start = time.monotonic()
            frame = await asyncio.to_thread(source.read_frame)
            live_frames.set(camera.id, frame)

            ok, encoded = await asyncio.to_thread(cv2.imencode, ".jpg", frame)
            if ok:
                # The frame and when it was taken, together: a reader of a frame that is no
                # longer being refreshed (capture stopped) can tell it is stale.
                await redis_client.mset(
                    {
                        f"latest_frame:{camera.id}": base64.b64encode(encoded.tobytes()).decode("ascii"),
                        f"latest_frame_at:{camera.id}": str(time.time()),
                    }
                )

            # Account for how long the read+encode+publish above took, so the loop holds
            # ~live_stream_fps even though each iteration isn't free - not interval flat on top.
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - start)))
    finally:
        await asyncio.to_thread(source.close)
