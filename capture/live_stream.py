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
from capture.frame_quality import SignalWatch, is_black_frame

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
        self._signal_lost: set[int] = set()

    def set(self, camera_id: int, frame: np.ndarray) -> None:
        self._frames[camera_id] = (frame, time.monotonic())

    def set_signal_lost(self, camera_id: int, lost: bool) -> None:
        """The camera delivers only black: its frames are not stored, and callers should not go and
        read the device themselves (they would get black too)."""
        (self._signal_lost.add if lost else self._signal_lost.discard)(camera_id)

    def signal_lost(self, camera_id: int) -> bool:
        return camera_id in self._signal_lost

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
        watch = SignalWatch()
        while True:
            start = time.monotonic()
            frame = await asyncio.to_thread(source.read_frame)

            change = watch.observe(frame)
            if change == "lost":
                live_frames.set_signal_lost(camera.id, True)
                logger.warning(
                    "Camera %s (%s) delivers only black frames: marked as no signal, and no frame is published "
                    "until it shows an image again (is it the right camera, is the lens covered, is another "
                    "application using it?)", camera.id, camera.name,
                )
            elif change == "back":
                live_frames.set_signal_lost(camera.id, False)
                logger.info("Camera %s (%s) delivers images again", camera.id, camera.name)

            # A black frame is fresh but says nothing: leaving it out lets the frame's age grow, which is how the
            # web (and the stream) tell "no signal" from live video.
            ok = False
            if not is_black_frame(frame):
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
