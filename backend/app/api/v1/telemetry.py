from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Printer, PrintJob, TelemetrySample
from app.db.session import get_db
from app.schemas.telemetry import ChainVerificationRead, JobTelemetryRead, PrinterEventRead, TelemetryPoint
from app.services import telemetry
from app.services.printer_events import list_events, verify_chain

router = APIRouter(tags=["telemetry"], dependencies=[Depends(get_current_user)])

_SAMPLE_COLUMNS = [getattr(TelemetrySample, name) for name in ("ts", *telemetry.SAMPLE_FIELDS, "extra")]


async def _get_printer_or_404(printer_id: int, db: AsyncSession) -> Printer:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    return printer


async def _get_job_or_404(job_id: int, db: AsyncSession) -> PrintJob:
    job = await db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found")
    return job


@router.get("/print-jobs/{job_id}/telemetry", response_model=JobTelemetryRead)
async def get_job_telemetry(
    job_id: int,
    max_points: int = Query(default=1500, ge=10, le=20000),
    db: AsyncSession = Depends(get_db),
) -> JobTelemetryRead:
    await _get_job_or_404(job_id, db)
    result = await db.execute(
        select(*_SAMPLE_COLUMNS).where(TelemetrySample.print_job_id == job_id).order_by(TelemetrySample.ts)
    )
    rows = [telemetry.clean_row(dict(row._mapping)) for row in result]
    points, bucket_seconds = telemetry.downsample(rows, max_points)
    return JobTelemetryRead(
        job_id=job_id,
        samples=len(rows),
        bucket_seconds=bucket_seconds,
        points=[TelemetryPoint(**point) for point in points],
    )


@router.get("/printers/{printer_id}/telemetry/latest")
async def get_latest_reading(printer_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _get_printer_or_404(printer_id, db)
    reading = telemetry.latest_readings.get(printer_id)
    if reading is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No reading yet: the printer is not connected")
    return reading


def _csv(value: str | None) -> list[str] | None:
    return [item.strip() for item in value.split(",") if item.strip()] if value else None


@router.get("/printers/{printer_id}/events", response_model=list[PrinterEventRead])
async def get_printer_events(
    printer_id: int,
    job_id: int | None = None,
    before_id: int | None = None,
    origin: str | None = Query(default=None, description="comma-separated, e.g. console,external"),
    event_type: str | None = Query(default=None, description="comma-separated"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list:
    await _get_printer_or_404(printer_id, db)
    return await list_events(
        db,
        printer_id,
        job_id=job_id,
        before_id=before_id,
        origins=_csv(origin),
        event_types=_csv(event_type),
        limit=limit,
    )


@router.get("/print-jobs/{job_id}/events", response_model=list[PrinterEventRead])
async def get_job_events(
    job_id: int, limit: int = Query(default=500, ge=1, le=5000), db: AsyncSession = Depends(get_db)
) -> list:
    job = await _get_job_or_404(job_id, db)
    return await list_events(db, job.printer_id, job_id=job_id, limit=limit)


@router.get("/printers/{printer_id}/events/verify", response_model=ChainVerificationRead)
async def verify_printer_events(printer_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _get_printer_or_404(printer_id, db)
    return await verify_chain(db, printer_id)
