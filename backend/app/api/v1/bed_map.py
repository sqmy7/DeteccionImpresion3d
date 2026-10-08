from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import Camera, CameraCalibration, Printer, PrintJob, User
from app.db.session import get_db
from app.schemas.bed_map import BedHeatmapRead, CalibrationCreate, CalibrationRead, JobBedMapRead
from app.services import bed_map, defect_map, telemetry

router = APIRouter(tags=["bed-map"], dependencies=[Depends(get_current_user)])

# Above this the bed was moving when the calibration frame was taken (mm/s).
_STILL_SPEED = 1.0


async def _get_camera_or_404(camera_id: int, db: AsyncSession) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


@router.get("/cameras/{camera_id}/calibration", response_model=CalibrationRead)
async def get_calibration(camera_id: int, db: AsyncSession = Depends(get_db)) -> CameraCalibration:
    await _get_camera_or_404(camera_id, db)
    calibration = await db.scalar(
        select(CameraCalibration)
        .where(CameraCalibration.camera_id == camera_id)
        .order_by(CameraCalibration.created_at.desc(), CameraCalibration.id.desc())
        .limit(1)
    )
    if calibration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not calibrated")
    return calibration


@router.get("/cameras/{camera_id}/calibrations", response_model=list[CalibrationRead])
async def list_calibrations(camera_id: int, db: AsyncSession = Depends(get_db)) -> list[CameraCalibration]:
    await _get_camera_or_404(camera_id, db)
    result = await db.execute(
        select(CameraCalibration)
        .where(CameraCalibration.camera_id == camera_id)
        .order_by(CameraCalibration.created_at.desc(), CameraCalibration.id.desc())
    )
    return list(result.scalars().all())


@router.post("/cameras/{camera_id}/calibration", response_model=CalibrationRead, status_code=status.HTTP_201_CREATED)
async def create_calibration(
    camera_id: int,
    payload: CalibrationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> CalibrationRead:
    """Only reads the printer's state (its last reported Y and bed size); nothing is sent to it."""
    camera = await _get_camera_or_404(camera_id, db)
    geometry = await defect_map.printer_geometry(db, camera.printer_id)
    bed_points = payload.bed_points or defect_map.default_bed_points(geometry)
    warnings: list[str] = []

    reference_y = payload.reference_y if payload.bed_moves_in_image else None
    if payload.bed_moves_in_image and reference_y is None:
        reading = telemetry.latest_readings.get(camera.printer_id) or {}
        if reading.get("y") is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The bed moves in the image but the toolhead's Y is unknown: connect the printer or send reference_y",
            )
        reference_y = reading["y"]
        if (reading.get("velocity") or 0.0) > _STILL_SPEED:
            warnings.append("bed_was_moving")

    try:
        calibration = bed_map.build_calibration(
            list(payload.image_points),
            list(bed_points),
            payload.image_width,
            payload.image_height,
            payload.bed_moves_in_image,
            reference_y,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    camera_model = calibration.camera
    if camera_model is None:
        warnings.append("camera_not_estimated")
    elif not camera_model.focal_estimated:
        warnings.append("focal_assumed")

    row = CameraCalibration(
        camera_id=camera.id,
        created_by=user.id,
        image_points=[list(point) for point in payload.image_points],
        bed_points=[list(point) for point in bed_points],
        image_width=payload.image_width,
        image_height=payload.image_height,
        bed_moves_in_image=payload.bed_moves_in_image,
        reference_y=reference_y,
        focal_px=round(camera_model.focal_px, 1) if camera_model else None,
        camera_position=[round(value, 1) for value in camera_model.center] if camera_model else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CalibrationRead.model_validate(row).model_copy(update={"warnings": warnings})


@router.get("/print-jobs/{job_id}/bed-map", response_model=JobBedMapRead)
async def get_job_bed_map(job_id: int, db: AsyncSession = Depends(get_db)) -> JobBedMapRead:
    job = await db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found")
    defects, skipped = await defect_map.locate_job_defects(db, job)
    calibrated = await db.execute(
        select(CameraCalibration.camera_id)
        .join(Camera, Camera.id == CameraCalibration.camera_id)
        .where(Camera.printer_id == job.printer_id)
        .distinct()
    )
    return JobBedMapRead(
        job_id=job.id,
        geometry=telemetry.geometry_with_file_info(job.geometry, job.file_name),
        calibrated_cameras=sorted(calibrated.scalars().all()),
        defects=defects,
        skipped_boxes=skipped,
        head_path=await defect_map.job_head_path(db, job.id),
    )


@router.get("/printers/{printer_id}/bed-heatmap", response_model=BedHeatmapRead)
async def get_bed_heatmap(
    printer_id: int,
    cell_mm: float = Query(default=20.0, ge=5.0, le=100.0),
    classes: str | None = Query(default=None, description="comma-separated defect classes"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await db.get(Printer, printer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    wanted = {name.strip() for name in classes.split(",") if name.strip()} if classes else None
    return await defect_map.printer_heatmap(db, printer_id, cell_mm, wanted)


@router.get("/printers/{printer_id}/geometry")
async def get_printer_geometry(printer_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    if await db.get(Printer, printer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    geometry = await defect_map.printer_geometry(db, printer_id)
    if geometry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No bed geometry reported yet")
    return geometry
