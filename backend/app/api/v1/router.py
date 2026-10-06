from fastapi import APIRouter

from app.api.v1 import alerts, auth, cameras, detections, layers, model_versions, print_jobs, printers, ws

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(printers.router)
router.include_router(cameras.router)
router.include_router(cameras.stream_router)
router.include_router(print_jobs.router)
router.include_router(layers.router)
router.include_router(layers.thumbnail_router)
router.include_router(model_versions.router)
router.include_router(detections.router)
router.include_router(alerts.router)
router.include_router(ws.router)
