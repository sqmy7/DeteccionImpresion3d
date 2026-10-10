from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.models import Printer, PrintJob, User
from app.db.session import get_db
from app.schemas.insights import CostSettings, CostSettingsRead, JobCostRead, JobFusionRead, PrinterHealthRead
from app.services import costs, fusion, health, report

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


@router.get("/print-jobs/{job_id}/cost", response_model=JobCostRead)
async def get_job_cost(job_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Estimated cost of the job: filament used and the heaters' energy, at the configured prices."""
    job = await _get_job_or_404(job_id, db)
    return await costs.job_cost(db, job)


@router.get("/print-jobs/{job_id}/report.pdf", response_class=Response)
async def get_job_report(job_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    """The job's PDF report, built with the data as it is now (a running job gets a partial one)."""
    job = await _get_job_or_404(job_id, db)
    content = await report.build_report(db, job)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="reporte_trabajo_{job.id}.pdf"'},
    )


@router.get("/settings/costs", response_model=CostSettingsRead)
async def get_cost_settings(db: AsyncSession = Depends(get_db)) -> dict:
    return await costs.get_settings(db)


@router.put("/settings/costs", response_model=CostSettingsRead)
async def put_cost_settings(
    payload: CostSettings, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)
) -> dict:
    return await costs.save_settings(db, payload.model_dump(), user.id)
