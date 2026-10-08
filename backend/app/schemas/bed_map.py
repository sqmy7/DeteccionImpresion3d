from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CalibrationCreate(BaseModel):
    # The four marks on the frame, normalized 0..1, in the same order as bed_points.
    image_points: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    # Bed millimetres of those marks; by default the bed corners from Klipper's axis limits, in
    # the order front-left, front-right, back-right, back-left.
    bed_points: list[tuple[float, float]] | None = Field(default=None, min_length=4, max_length=4)
    image_width: int = Field(gt=0, le=10000)
    image_height: int = Field(gt=0, le=10000)
    # True when the camera stays still while the bed slides along Y (bed-slinger, camera on the
    # frame or the table); False when the camera rides on the bed or the bed doesn't move in XY.
    bed_moves_in_image: bool = True
    # Toolhead Y when the frame was taken; by default the latest reading.
    reference_y: float | None = None
    # The camera's known focal length in pixels at this resolution (the C922 at 1280x720 is ~907).
    # When given it is used as is instead of being estimated from the marks, which a single view of
    # a plane estimates badly when the far corners are hard to place.
    focal_px: float | None = Field(default=None, gt=0, le=100000)

    @field_validator("image_points")
    @classmethod
    def _inside_the_frame(cls, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if any(not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0) for u, v in points):
            raise ValueError("image points must be normalized to 0..1")
        return points


class MarkErrorRead(BaseModel):
    error_px: float
    error_mm: float


class CalibrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    created_at: datetime
    created_by: int | None
    image_points: list[list[float]]
    bed_points: list[list[float]]
    image_width: int
    image_height: int
    bed_moves_in_image: bool
    reference_y: float | None
    focal_px: float | None
    camera_position: list[float] | None
    # Codes the web explains: "bed_was_moving", "camera_not_estimated", "focal_assumed".
    warnings: list[str] = Field(default_factory=list)
    # "estimated" from the marks, "assumed" (field of view of the C922) or "fixed" (given by the user).
    focal_source: str | None = None
    typical_focal_px: float | None = None
    # Per mark, in order: how far the camera model puts the corner from where it was marked.
    marks: list[MarkErrorRead] | None = None
    # The same with the camera's known focal, shown when the one in use is a different one: it tells
    # which mark is off before recalibrating.
    marks_at_typical_focal: list[MarkErrorRead] | None = None


class LocatedDefect(BaseModel):
    detection_id: int
    box_index: int  # position of the box in the detection's raw_output["detections"]
    capture_id: int
    camera_id: int
    calibration_id: int
    calibration_after_capture: bool
    layer_number: int
    z: float
    class_name: str | None
    confidence: float | None
    box: list[float]
    x: float
    y: float
    uncertainty_mm: float
    reliable: bool
    parallax_mm: float
    shift_mm: float
    object: str | None
    head: dict[str, float | None]
    current_object: str | None


class JobBedMapRead(BaseModel):
    job_id: int
    geometry: dict[str, Any] | None
    calibrated_cameras: list[int]
    defects: list[LocatedDefect]
    # Defect boxes that could not be placed: camera never calibrated, or an early box format.
    skipped_boxes: int
    head_path: list[list[float]]


class BedHeatmapRead(BaseModel):
    printer_id: int
    cell_mm: float
    width_mm: float
    depth_mm: float
    # counts[row][column]; row 0 is the front of the bed, column 0 the left.
    counts: list[list[int]]
    jobs: int
    located: int
    unreliable: int
    skipped_boxes: int
    bed_mesh: dict[str, Any] | None
