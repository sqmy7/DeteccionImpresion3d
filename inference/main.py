import asyncio
import json
import logging
import os
from pathlib import Path

import cv2
import redis.asyncio as redis
from sqlalchemy import select

from config import settings
from db import async_session_factory
from db_models import Camera, Detection, ModelVersion
from model import DefectDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STREAM_NAME = "captures:pending"
CONSUMER_GROUP = "inference-workers"
CONSUMER_NAME = f"worker-{os.getpid()}"

_RECONNECT_DELAY_SECONDS = 10


async def _ensure_consumer_group(redis_client) -> None:
    try:
        # id="0": a fresh group reads from the start of the stream, not just new
        # entries - matters for delivery guarantees if the worker starts after
        # capture already queued something.
        await redis_client.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _load_metrics_sidecar() -> dict | None:
    """Training metrics (per-class mAP etc.) can't be read from the .onnx itself - Ultralytics
    only embeds export args there, not results. They come from an optional sidecar file next to
    the model, e.g. models/best_int8.metrics.json, copied over from the Colab validation output.
    Absent sidecar -> metrics stays NULL; a malformed one fails loudly instead of being ignored."""
    path = settings.models_dir / f"{Path(settings.onnx_filename).stem}.metrics.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object, got {type(data).__name__}")
    return data


async def _get_or_create_model_version_id(class_names: list[str]) -> int:
    file_path = str(settings.models_dir / settings.onnx_filename)
    metrics = _load_metrics_sidecar()

    async with async_session_factory() as db:
        result = await db.execute(select(ModelVersion).where(ModelVersion.name == settings.onnx_version_name))
        model_version = result.scalar_one_or_none()

        if model_version is None:
            model_version = ModelVersion(
                name=settings.onnx_version_name, file_path=file_path, classes=class_names, metrics=metrics
            )
            db.add(model_version)
            await db.commit()
            await db.refresh(model_version)
            return model_version.id

        if model_version.classes != class_names:
            raise RuntimeError(
                f"model_versions row '{model_version.name}' (id={model_version.id}) was registered with classes "
                f"{model_version.classes}, but the loaded model reports {class_names}. Set ONNX_VERSION_NAME to a "
                "new name so this model gets its own row instead of being attributed to the old one."
            )

        # Same version, same classes: only metrics may legitimately change (e.g. a sidecar added later).
        if metrics is not None and model_version.metrics != metrics:
            model_version.metrics = metrics
            await db.commit()
        return model_version.id


async def _get_camera_roi(camera_id: int) -> dict | None:
    async with async_session_factory() as db:
        camera = await db.get(Camera, camera_id)
        return camera.roi if camera is not None else None


def _touch_heartbeat() -> None:
    settings.heartbeat_path.touch()


async def run_forever() -> None:
    while True:
        try:
            await _consume()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Inference worker crashed, restarting in %ss", _RECONNECT_DELAY_SECONDS)
        await asyncio.sleep(_RECONNECT_DELAY_SECONDS)


async def _consume() -> None:
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    await _ensure_consumer_group(redis_client)

    detector = DefectDetector(str(settings.models_dir / settings.onnx_filename))
    model_version_id = await _get_or_create_model_version_id(detector.class_names)
    logger.info(
        "Inference worker ready (model=%s, version=%s, model_version_id=%s, classes=%s, confidence_threshold=%s), consuming %s",
        settings.onnx_filename,
        settings.onnx_version_name,
        model_version_id,
        detector.class_names,
        settings.confidence_threshold,
        STREAM_NAME,
    )

    while True:
        _touch_heartbeat()
        response = await redis_client.xreadgroup(
            CONSUMER_GROUP, CONSUMER_NAME, {STREAM_NAME: ">"}, count=1, block=5000
        )
        if not response:
            continue

        for _stream, messages in response:
            for message_id, fields in messages:
                try:
                    await _process_message(redis_client, detector, model_version_id, fields)
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                except Exception:
                    # Not ack'd on purpose - Redis Streams consumer groups exist precisely so a
                    # failed message stays pending for retry/reclaim instead of being silently lost.
                    logger.exception("Failed processing message %s, leaving pending for retry: %r", message_id, fields)


async def _process_message(redis_client, detector: DefectDetector, model_version_id: int, fields: dict) -> None:
    capture_id = int(fields["capture_id"])
    printer_id = int(fields["printer_id"])
    job_id = int(fields["job_id"])
    layer_number = int(fields["layer_number"])
    camera_id = int(fields["camera_id"])
    image_path = fields["image_path"]  # relative to storage_root - see capture_worker.py's note

    absolute_path = settings.storage_root / image_path
    frame = cv2.imread(str(absolute_path))
    if frame is None:
        raise RuntimeError(f"Could not read image at '{absolute_path}' for capture {capture_id}")

    full_height, full_width = frame.shape[:2]
    roi = await _get_camera_roi(camera_id)
    if roi:
        roi_x, roi_y, roi_w, roi_h = int(roi["x"]), int(roi["y"]), int(roi["w"]), int(roi["h"])
        frame = frame[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
    else:
        roi_x, roi_y, roi_w, roi_h = 0, 0, full_width, full_height

    result = detector.predict(frame)
    # The boxes above are normalized to the region the model saw. Keeping that region (and the
    # full frame's size) with them lets the bed map place them on the full frame later, even if
    # the camera's ROI is changed afterwards.
    result["raw_output"]["frame"] = {
        "width": full_width,
        "height": full_height,
        "roi": {"x": roi_x, "y": roi_y, "w": roi_w, "h": roi_h},
    }

    async with async_session_factory() as db:
        detection = Detection(
            capture_id=capture_id,
            model_version_id=model_version_id,
            has_defect=result["has_defect"],
            max_confidence=result["max_confidence"],
            defect_classes=result["defect_classes"],
            raw_output=result["raw_output"],
        )
        db.add(detection)
        await db.commit()
        await db.refresh(detection)

    await redis_client.publish(
        "events:detection_result",
        json.dumps(
            {
                "detection_id": detection.id,
                "capture_id": capture_id,
                "printer_id": printer_id,
                "job_id": job_id,
                "layer_number": layer_number,
                "camera_id": camera_id,
                "has_defect": detection.has_defect,
                "max_confidence": result["max_confidence"],
                "defect_classes": result["defect_classes"],
            }
        ),
    )

    # Separate channel from detection_result on purpose: the timeline only needs the summary
    # above and every existing consumer of detection_result already ignores unknown fields, but
    # a per-box list is a different concern (live overlay) with a different shape, so it gets its
    # own event instead of growing detection_result's payload for consumers that don't need it.
    # Coordinates are normalized 0..1 against the FULL captured frame (full_width/full_height) -
    # i.e. what VideoFeed's <img> actually shows - not the ROI-cropped region the model saw, so
    # the frontend can draw them straight over the video without knowing about ROI cropping.
    boxes = [
        {
            "class": d["class"],
            "confidence": d["confidence"],
            "x1": round((roi_x + d["box"][0] * roi_w) / full_width, 4),
            "y1": round((roi_y + d["box"][1] * roi_h) / full_height, 4),
            "x2": round((roi_x + d["box"][2] * roi_w) / full_width, 4),
            "y2": round((roi_y + d["box"][3] * roi_h) / full_height, 4),
        }
        for d in result["raw_output"]["detections"]
    ]
    await redis_client.publish(
        "events:detection_boxes",
        json.dumps(
            {
                "detection_id": detection.id,
                "capture_id": capture_id,
                "printer_id": printer_id,
                "job_id": job_id,
                "layer_number": layer_number,
                "camera_id": camera_id,
                "boxes": boxes,
            }
        ),
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
