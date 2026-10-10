from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    analytics,
    auth,
    bed_map,
    cameras,
    detections,
    incidents,
    insights,
    layers,
    model_versions,
    print_jobs,
    printers,
    telemetry,
    ws,
)

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
router.include_router(incidents.router)
router.include_router(telemetry.router)
router.include_router(bed_map.router)
router.include_router(analytics.router)
router.include_router(insights.router)
router.include_router(ws.router)
