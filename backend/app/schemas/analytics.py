from datetime import datetime

from pydantic import BaseModel


class AnalyticsTotals(BaseModel):
    jobs: int
    success_rate: float | None = None  # completed / finished jobs
    print_hours: float | None = None
    layers: int | None = None
    layers_with_defect: int | None = None
    defect_rate: float | None = None
    interventions: int | None = None
    filament_m: float | None = None
    # Sum of the jobs' cost estimates (filament + heater energy) at the configured prices.
    cost: float | None = None


class JobAnalytics(BaseModel):
    id: int
    printer_id: int
    file_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_s: float
    layers: int
    layers_with_defect: int
    defect_rate: float | None
    classes: dict[str, int]
    interventions: dict[str, int]
    telemetry_samples: int
    # Mean and worst absolute gap between temperature and target while printing layers.
    nozzle_error_mean_c: float | None
    nozzle_error_max_c: float | None
    bed_error_mean_c: float | None
    filament_m: float | None
    cost: float | None = None  # estimate: filament + heater energy (one sample per second)


class AnalyticsSummaryRead(BaseModel):
    totals: AnalyticsTotals
    status_counts: dict[str, int]
    defects_by_class: dict[str, int]
    interventions_by_origin: dict[str, int]
    jobs: list[JobAnalytics]
    currency: str | None = None
    cost_settings_are_default: bool | None = None
