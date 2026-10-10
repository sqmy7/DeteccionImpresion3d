from datetime import datetime

from pydantic import BaseModel, Field


class FusionSignal(BaseModel):
    key: str
    label: str
    unit: str
    operator: str  # how the value is compared with the threshold: ">", ">=" or "<="
    threshold: float
    weight: float
    value: float | None  # None: the window had no data for this signal
    met: bool


class FusionWindow(BaseModel):
    source: str | None  # "telemetry" (1 Hz samples), "layer_snapshot" (older jobs) or None (no data)
    samples: int
    layers: list[int]


class FusionItem(BaseModel):
    detection_id: int
    box_index: int  # position of the box in the detection's raw_output["detections"]
    layer_number: int
    class_name: str | None
    confidence: float | None
    score: float
    signals: list[FusionSignal]
    window: FusionWindow


class FusionMethodSignal(BaseModel):
    key: str
    label: str
    unit: str
    operator: str
    threshold: float
    weight: float
    rationale: str
    classes: list[str]


class FusionMethod(BaseModel):
    formula: str
    window: str
    weights: dict[str, float]
    calibrated: bool
    signals: list[FusionMethodSignal]


class JobFusionRead(BaseModel):
    job_id: int
    items: list[FusionItem]
    method: FusionMethod


class HealthBaseline(BaseModel):
    n: int
    mean: float
    std: float
    upper: float
    lower: float


class HealthPoint(BaseModel):
    job_id: int
    started_at: datetime
    file_name: str
    value: float
    target: float | None
    flags: list[str]  # control-chart rules this job broke: beyond_3sigma, two_of_three_beyond_2sigma, eight_on_worse_side


class HealthMetric(BaseModel):
    key: str
    label: str
    unit: str
    worse: str  # "up" or "down"
    status: str  # "normal", "attention" or "insufficient"
    baseline: HealthBaseline | None
    findings: list[str]
    points: list[HealthPoint]


class HealthHeater(BaseModel):
    heater: str
    label: str
    target_bucket: float | None  # the target the comparison is made at (latest job's, in 5 °C steps)
    metrics: list[HealthMetric]


class HealthMethodMetric(BaseModel):
    key: str
    label: str
    unit: str
    worse: str
    description: str


class HealthMethod(BaseModel):
    settle_delta_c: float
    in_range_c: float
    min_steady_samples: int
    min_heatup_c: float
    target_bucket_c: float
    min_baseline_jobs: int
    max_baseline_jobs: int
    metrics: list[HealthMethodMetric]


class PrinterHealthRead(BaseModel):
    printer_id: int
    jobs_considered: int
    jobs_with_telemetry: int
    heaters: list[HealthHeater]
    method: HealthMethod

class CostSettings(BaseModel):
    """What the team sets for the cost estimate. Bounds only catch typos."""

    currency: str = Field(min_length=1, max_length=8)
    filament_price_per_kg: float = Field(ge=0, le=10_000_000)
    energy_price_per_kwh: float = Field(ge=0, le=100_000)
    extruder_heater_w: float = Field(ge=0, le=1000)
    bed_heater_w: float = Field(ge=0, le=3000)
    filament_diameter_mm: float = Field(ge=1.0, le=3.5)
    default_density_g_cm3: float = Field(ge=0.5, le=3.0)


class CostSettingsRead(CostSettings):
    is_default: bool  # nobody saved values yet: the prices are examples
    updated_at: datetime | None


class FilamentCost(BaseModel):
    used_mm: float | None  # print_stats.filament_used: what the printer commanded to extrude
    used_g: float | None
    method: str | None  # "slicer" (its grams per mm) or "density" (material density x diameter)
    density: float | None
    material: str | None
    cost: float | None
    estimated_mm: float | None  # the slicer's estimate for the whole file
    estimated_g: float | None


class EnergyCost(BaseModel):
    extruder_wh: float
    bed_wh: float
    total_kwh: float
    covered_seconds: int  # time covered by telemetry (gaps over 5 s are not counted)
    cost: float


class JobCostRead(BaseModel):
    job_id: int
    currency: str
    filament: FilamentCost
    energy: EnergyCost | None
    total_cost: float | None
    settings: CostSettings
    settings_are_default: bool