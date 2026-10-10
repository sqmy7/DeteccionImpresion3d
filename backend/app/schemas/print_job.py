from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import JobStatus


class PrintJobCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    octoprint_job_id: str | None = Field(default=None, max_length=100)
    estimated_layers: int | None = Field(default=None, ge=1)


class PrintJobTransition(BaseModel):
    status: JobStatus


class PrintJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    printer_id: int
    octoprint_job_id: str | None
    file_name: str
    status: JobStatus
    estimated_layers: int | None
    started_at: datetime
    ended_at: datetime | None
    # How long the job really printed, by the printer's own clock (Klipper's print_duration, kept with
    # each telemetry sample since 2026-10-08). None for older jobs, which have no such reading:
    # started_at..ended_at only says how long PrintWatch followed the job, which is less than the
    # print when it joined late (job 43: followed 2 h 45 min of a 6 h print).
    printed_s: float | None = None


class TimelineEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    layer_number: int
    z_height: Decimal | None
    capture_id: int | None
    has_defect: bool
    defect_classes: list[str] = Field(default_factory=list)
    thumbnail_url: str | None


class ModelVersionSummary(BaseModel):
    id: int
    name: str


class JobSummaryRead(BaseModel):
    job_id: int
    current_layer: int | None
    total_layers_recorded: int
    layers_captured: int
    layers_ok: int
    layers_with_defect: int
    defect_class_counts: dict[str, int]
    active_alerts_count: int
    latest_model_version: ModelVersionSummary | None
