from datetime import datetime

from pydantic import BaseModel


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