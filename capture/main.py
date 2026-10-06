import asyncio
import json
import logging

import redis.asyncio as redis
from app.db.models import Camera
from sqlalchemy import select

from capture.capture_worker import handle_layer_ready
from capture.config import settings
from capture.db import async_session_factory
from capture.live_stream import run_live_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 10


async def run_forever() -> None:
    while True:
        try:
            await _listen()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Capture process's Redis connection failed, reconnecting in %ss", _RECONNECT_DELAY_SECONDS)
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


async def _listen() -> None:
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("layer_ready:*")
    logger.info("Capture process listening on layer_ready:*")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        try:
            payload = json.loads(message["data"])
        except json.JSONDecodeError:
            logger.warning("Discarding non-JSON layer_ready payload: %r", message["data"])
            continue

        try:
            await handle_layer_ready(async_session_factory, redis_client, payload)
        except Exception:
            logger.exception("Failed handling layer_ready payload %r, continuing", payload)


async def _active_cameras() -> list[Camera]:
    async with async_session_factory() as db:
        result = await db.execute(select(Camera).where(Camera.is_active.is_(True)))
        return list(result.scalars().all())


async def main() -> None:
    cameras = await _active_cameras()
    logger.info("Starting continuous live stream for %s active camera(s)", len(cameras))
    # Two independent, concurrently-running concerns in this one process: the layer_ready
    # listener (unchanged - triggers the once-per-layer capture + inference) and one continuous
    # live-stream loop per camera (new - just publishes frames for the video feed, no inference).
    await asyncio.gather(run_forever(), *(run_live_stream(camera) for camera in cameras))


if __name__ == "__main__":
    asyncio.run(main())
