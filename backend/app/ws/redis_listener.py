import json
import logging

import redis.asyncio as redis

from app.core.config import settings
from app.db.session import async_session_factory
from app.services import incidents
from app.services.auto_pause import auto_pause_manager
from app.services.jam_detection import check_jam_trend
from app.ws.manager import manager

logger = logging.getLogger(__name__)

# Channel naming: events:<event_type with '.' -> '_'>. Publishers (inference worker,
# OctoPrint client, or manual test scripts) publish just the event's `data` payload here;
# this listener wraps it in the {type, timestamp, data} envelope before relaying over WS.
CHANNEL_EVENT_TYPES = {
    "events:printer_status": "printer.status",
    "events:layer_captured": "layer.captured",
    "events:detection_result": "detection.result",
    "events:detection_boxes": "detection.boxes",
    "events:detection_alert": "detection.alert",
    "events:job_started": "job.started",
    "events:job_completed": "job.completed",
    "events:job_failed": "job.failed",
    "events:job_cancelled": "job.cancelled",
}


async def redis_listener(redis_client: "redis.Redis") -> None:
    channels = {f"{settings.redis_channel_prefix}{name}": event_type for name, event_type in CHANNEL_EVENT_TYPES.items()}
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*channels.keys())

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        event_type = channels.get(message["channel"])
        if event_type is None:
            continue

        try:
            data = json.loads(message["data"])
        except (TypeError, json.JSONDecodeError):
            logger.warning("Discarding non-JSON payload on channel %s", message["channel"])
            continue

        await manager.broadcast(event_type, data)

        if event_type == "detection.result" and data.get("has_defect"):
            # An incident opens for an eligible class over the threshold (INCIDENT_CLASSES / INCIDENT_MIN_CONFIDENCE).
            try:
                await incidents.record_detection(async_session_factory, data)
            except Exception:
                logger.exception("Incident check failed for detection.result payload %r", data)

        if event_type == "detection.result" and "under_extrusion" in data.get("defect_classes", []):
            try:
                async with async_session_factory() as db:
                    await check_jam_trend(
                        db, job_id=data["job_id"], camera_id=data["camera_id"], detection_id=data["detection_id"]
                    )
            except Exception:
                logger.exception("Jam-trend check failed for detection.result payload %r", data)

        if event_type == "detection.result" and "spaghetti" in data.get("defect_classes", []):
            try:
                await auto_pause_manager.check_spaghetti_streak(
                    async_session_factory,
                    job_id=data["job_id"],
                    camera_id=data["camera_id"],
                    printer_id=data["printer_id"],
                )
            except Exception:
                logger.exception("Spaghetti auto-pause check failed for detection.result payload %r", data)
