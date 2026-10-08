from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import Camera, CameraCalibration, Printer, PrintJob, User
from app.db.session import get_db
from app.schemas.bed_map import BedHeatmapRead, CalibrationCreate, CalibrationRead, JobBedMapRead, MarkErrorRead
from app.services import bed_map, defect_map, telemetry

router = APIRouter(tags=["bed-map"], dependencies=[Depends(get_current_user)])

# Above this the bed was moving when the calibration frame was taken (mm/s).
_STILL_SPEED = 1.0


async def _get_camera_or_404(camera_id: int, db: AsyncSession) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


def _mark_errors(marks) -> list[MarkErrorRead] | None:
    return [MarkErrorRead(error_px=round(m.error_px, 1), error_mm=round(m.error_mm, 1)) for m in marks] if marks else None


def _describe(row: CameraCalibration, extra_warnings: tuple[str, ...] = ()) -> CalibrationRead:
    """The stored calibration plus what is derived from it every time (no migration: the marks, the
    bed corners and the focal in use are all stored): the focal's source, the marks' reprojection
    error and the warnings."""
    read = CalibrationRead.model_validate(row)
    try:
        calibration = defect_map.calibration_from_row(row)
    except ValueError:
        return read.model_copy(update={"warnings": list(extra_warnings)})
    camera = calibration.camera
    typical = bed_map.typical_focal_px(row.image_width, row.image_height)
    at_typical = None
    if camera is not None and abs(camera.focal_px - typical) > 1.0:
        try:
            check = bed_map.build_calibration(
                [tuple(point) for point in row.image_points],
                [tuple(point) for point in row.bed_points],
                row.image_width,
                row.image_height,
                row.bed_moves_in_image,
                row.reference_y,
                fixed_focal_px=typical,
            )
            at_typical = _mark_errors(check.marks)
        except ValueError:
            at_typical = None
    warnings = [*extra_warnings, *bed_map.calibration_warnings(calibration)]
    # With a focal other than the C922's, say which marks the known focal would not accept.
    far_mm = bed_map.FAR_MARK_FRACTION * calibration.bed_size
    if at_typical and any(mark.error_mm > far_mm for mark in at_typical) and "mark_far_from_corner" not in warnings:
        warnings.append("mark_far_at_typical_focal")
    return read.model_copy(
        update={
            "warnings": warnings,
            "focal_source": camera.focal_source if camera else None,
            "typical_focal_px": round(typical, 1),
            "marks": _mark_errors(calibration.marks),
            "marks_at_typical_focal": at_typical,
        }
    )


@router.get("/cameras/{camera_id}/calibration", response_model=CalibrationRead)
async def get_calibration(camera_id: int, db: AsyncSession = Depends(get_db)) -> CalibrationRead:
    await _get_camera_or_404(camera_id, db)
    calibration = await db.scalar(
        select(CameraCalibration)
        .where(CameraCalibration.camera_id == camera_id)
        .order_by(CameraCalibration.created_at.desc(), CameraCalibration.id.desc())
        .limit(1)
    )
    if calibration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not calibrated")
    return _describe(calibration)


@router.get("/cameras/{camera_id}/calibrations", response_model=list[CalibrationRead])
async def list_calibrations(camera_id: int, db: AsyncSession = Depends(get_db)) -> list[CalibrationRead]:
    await _get_camera_or_404(camera_id, db)
    result = await db.execute(
        select(CameraCalibration)
        .where(CameraCalibration.camera_id == camera_id)
        .order_by(CameraCalibration.created_at.desc(), CameraCalibration.id.desc())
    )
    return [_describe(row) for row in result.scalars().all()]


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
    warnings: list[str] = []  # only what depends on this moment; the rest is derived by _describe

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
            fixed_focal_px=payload.focal_px,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    camera_model = calibration.camera
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
    return _describe(row, tuple(warnings))


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
