from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import Printer, PrintJob
from app.db.session import get_db
from app.schemas.print_job import JobSummaryRead, PrintJobCreate, PrintJobRead, PrintJobTransition, TimelineEntryRead
from app.services.auto_pause import auto_pause_manager
from app.services.print_jobs import create_print_job, read_jobs, transition_job_status
from app.services.timeline import get_job_summary, get_job_timeline

router = APIRouter(tags=["print-jobs"], dependencies=[Depends(get_current_user)])


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


@router.get("/printers/{printer_id}/print-jobs", response_model=list[PrintJobRead])
async def list_print_jobs(printer_id: int, db: AsyncSession = Depends(get_db)) -> list[PrintJobRead]:
    await _get_printer_or_404(printer_id, db)
    result = await db.execute(select(PrintJob).where(PrintJob.printer_id == printer_id).order_by(PrintJob.id))
    return await read_jobs(db, list(result.scalars().all()))


@router.post(
    "/printers/{printer_id}/print-jobs",
    response_model=PrintJobRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_print_job_endpoint(
    printer_id: int, payload: PrintJobCreate, db: AsyncSession = Depends(get_db)
) -> PrintJob:
    return await create_print_job(db, printer_id, payload)


@router.get("/print-jobs/{job_id}", response_model=PrintJobRead)
async def get_print_job(job_id: int, db: AsyncSession = Depends(get_db)) -> PrintJobRead:
    (read,) = await read_jobs(db, [await _get_job_or_404(job_id, db)])
    return read


@router.post("/print-jobs/{job_id}/transition", response_model=PrintJobRead, dependencies=[Depends(require_admin)])
async def transition_print_job(
    job_id: int, payload: PrintJobTransition, db: AsyncSession = Depends(get_db)
) -> PrintJob:
    job = await _get_job_or_404(job_id, db)
    return await transition_job_status(db, job, payload.status)


# "/print-jobs/{id}/timeline", not "/jobs/{id}/timeline" as first drafted in the contract -
# every other job route in this API already uses "print-jobs", so this matches that instead
# of introducing a second, inconsistent alias.
@router.get("/print-jobs/{job_id}/timeline", response_model=list[TimelineEntryRead])
async def get_print_job_timeline(job_id: int, db: AsyncSession = Depends(get_db)) -> list[TimelineEntryRead]:
    await _get_job_or_404(job_id, db)
    entries = await get_job_timeline(db, job_id)
    return [TimelineEntryRead.model_validate(entry) for entry in entries]


@router.get("/print-jobs/{job_id}/summary", response_model=JobSummaryRead)
async def get_print_job_summary(job_id: int, db: AsyncSession = Depends(get_db)) -> JobSummaryRead:
    await _get_job_or_404(job_id, db)
    summary = await get_job_summary(db, job_id)
    return JobSummaryRead.model_validate(summary)


@router.post(
    "/print-jobs/{job_id}/auto-pause/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def abort_auto_pause(job_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await _get_job_or_404(job_id, db)
    aborted = await auto_pause_manager.abort(job_id)
    if not aborted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No auto-pause is currently pending for this job (already executed, aborted, or never triggered)",
        )
