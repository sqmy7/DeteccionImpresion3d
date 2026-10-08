from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobStatus, Printer, PrintJob
from app.schemas.print_job import PrintJobCreate
from app.ws.manager import manager

# Only forward transitions out of 'running' are valid; completed/failed/cancelled are terminal.
_ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.running: {JobStatus.completed, JobStatus.failed, JobStatus.cancelled},
}

_STATUS_TO_EVENT_TYPE: dict[JobStatus, str] = {
    JobStatus.completed: "job.completed",
    JobStatus.failed: "job.failed",
    JobStatus.cancelled: "job.cancelled",
}


async def create_print_job(db: AsyncSession, printer_id: int, payload: PrintJobCreate) -> PrintJob:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer not found")

    result = await db.execute(
        select(PrintJob.id).where(PrintJob.printer_id == printer_id, PrintJob.status == JobStatus.running)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Printer already has a running print job",
        )

    job = PrintJob(
        printer_id=printer_id,
        file_name=payload.file_name,
        octoprint_job_id=payload.octoprint_job_id,
        estimated_layers=payload.estimated_layers,
        status=JobStatus.running,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await manager.broadcast(
        "job.started",
        {
            "job_id": job.id,
            "printer_id": job.printer_id,
            "file_name": job.file_name,
            "estimated_layers": job.estimated_layers,
            "started_at": job.started_at.isoformat(),
        },
    )
    return job


async def transition_job_status(
    db: AsyncSession, job: PrintJob, new_status: JobStatus, ended_at: datetime | None = None
) -> PrintJob:
    """ended_at defaults to now; callers that only learn about the end later pass a better time."""
    allowed = _ALLOWED_TRANSITIONS.get(job.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition print job from '{job.status.value}' to '{new_status.value}'",
        )

    job.status = new_status
    job.ended_at = ended_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)

    event_type = _STATUS_TO_EVENT_TYPE.get(new_status)
    if event_type is not None:
        await manager.broadcast(
            event_type,
            {
                "job_id": job.id,
                "printer_id": job.printer_id,
                "status": job.status.value,
                "ended_at": job.ended_at.isoformat(),
            },
        )
    return job
