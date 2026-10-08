from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Printer, PrintJob
from app.db.session import get_db
from app.schemas.insights import JobFusionRead, PrinterHealthRead
from app.services import fusion, health

router = APIRouter(tags=["insights"], dependencies=[Depends(get_current_user)])


async def _get_job_or_404(job_id: int, db: AsyncSession) -> PrintJob:
    job = await db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print job not found")
    return job


@router.get("/print-jobs/{job_id}/fusion", response_model=JobFusionRead)
async def get_job_fusion(job_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Combined score (model + telemetry) of each defect box. Informative only: alerts and the
    auto-pause don't use it."""
    job = await _get_job_or_404(job_id, db)
    return {"job_id": job.id, "items": await fusion.job_fusion(db, job), "method": fusion.method()}


@router.get("/printers/{printer_id}/health", response_model=PrinterHealthRead)
async def get_printer_health(printer_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Heater trends over the printer's finished jobs, each compared with its own past."""
    if await db.get(Printer, printer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")
    return await health.printer_health(db, printer_id)