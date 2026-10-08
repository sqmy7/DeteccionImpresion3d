"""Defects placed on the bed: each detection box is joined with the calibration its camera had
when the frame was captured, the layer's telemetry snapshot (toolhead Y and speed, for the
bed-slinger shift and its uncertainty), the layer height (for parallax) and the objects the file
declared, and then located with app/services/bed_map.py."""

import bisect
import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CameraCalibration, Detection, Layer, LayerCapture, PrintJob, TelemetrySample
from app.services import bed_map
from app.services.telemetry import latest_geometry

_DEFAULT_BED_MM = 260.0  # Creality Hi spec sheet, when Klipper hasn't reported its axis limits
_MAX_PATH_POINTS = 1500


def calibration_from_row(row: CameraCalibration) -> bed_map.Calibration:
    return bed_map.build_calibration(
        [tuple(point) for point in row.image_points],
        [tuple(point) for point in row.bed_points],
        row.image_width,
        row.image_height,
        row.bed_moves_in_image,
        row.reference_y,
    )


def bed_dimensions(geometry: dict | None) -> tuple[float, float]:
    """Width and depth of the bed in mm. Klipper's axis limits are the head's travel, not the bed:
    on the Creality Hi they are 285 x 273 (the filament cutter sits past the bed), against a
    260 x 260 bed. The bed mesh is symmetric about the bed, so mesh_min + mesh_max gives its size
    (10 + 250 = 260, the same as the spec sheet); without a mesh, the spec size, never more than the
    head can travel."""
    geometry = geometry or {}
    maximum = geometry.get("axis_maximum") or []
    mesh = geometry.get("bed_mesh") or {}
    sizes = []
    for axis in (0, 1):
        travel = float(maximum[axis]) if len(maximum) > axis and maximum[axis] else None
        try:
            size = float(mesh["mesh_min"][axis]) + float(mesh["mesh_max"][axis])
        except (KeyError, IndexError, TypeError, ValueError):
            size = _DEFAULT_BED_MM
        sizes.append(min(size, travel) if travel else size)
    return sizes[0], sizes[1]


def default_bed_points(geometry: dict | None) -> list[tuple[float, float]]:
    """The bed corners: (0,0) is the front-left corner."""
    width, depth = bed_dimensions(geometry)
    return [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]


def full_frame_box(box: list[float], frame: dict | None) -> tuple[float, float, float, float] | None:
    """A box normalized to the region the model saw, in normalized coordinates of the full frame.
    Detections stored before the region was recorded used the full frame (no ROI was ever set).
    Returns None for the few early detections stored in an older, non-normalized format."""
    if len(box) != 4 or any(not isinstance(value, (int, float)) or value < -0.01 or value > 1.01 for value in box):
        return None
    if not frame or not frame.get("roi") or not frame.get("width") or not frame.get("height"):
        return tuple(box)
    roi, width, height = frame["roi"], frame["width"], frame["height"]
    return (
        (roi["x"] + box[0] * roi["w"]) / width,
        (roi["y"] + box[1] * roi["h"]) / height,
        (roi["x"] + box[2] * roi["w"]) / width,
        (roi["y"] + box[3] * roi["h"]) / height,
    )


def _inside(polygon: list, x: float, y: float) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _distance_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def object_at(objects: list[dict], x: float, y: float, tolerance: float) -> str | None:
    """The declared object whose outline contains the point, else the nearest within tolerance."""
    nearest, nearest_distance = None, tolerance
    for obj in objects:
        polygon = obj.get("polygon") or []
        if len(polygon) < 3:
            continue
        if _inside(polygon, x, y):
            return obj.get("name")
        distance = min(
            _distance_to_segment(x, y, *a, *b) for a, b in zip(polygon, polygon[1:] + polygon[:1])
        )
        if distance <= nearest_distance:
            nearest, nearest_distance = obj.get("name"), distance
    return nearest


class _CalibrationHistory:
    """For each camera, the calibration in force when a frame was captured: the latest one made
    before it, else the first one made after (assuming the camera hadn't moved)."""

    def __init__(self, rows: list[CameraCalibration]) -> None:
        self._by_camera: dict[int, list[CameraCalibration]] = defaultdict(list)
        for row in sorted(rows, key=lambda row: row.created_at):
            self._by_camera[row.camera_id].append(row)
        self._built: dict[int, bed_map.Calibration] = {}

    def for_capture(self, camera_id: int, captured_at: datetime) -> tuple[CameraCalibration, bed_map.Calibration] | None:
        rows = self._by_camera.get(camera_id)
        if not rows:
            return None
        index = bisect.bisect_right([row.created_at for row in rows], captured_at) - 1
        row = rows[max(index, 0)]
        if row.id not in self._built:
            self._built[row.id] = calibration_from_row(row)
        return row, self._built[row.id]


async def locate_job_defects(db: AsyncSession, job: PrintJob) -> tuple[list[dict], int]:
    """Every defect box of the job with its place on the bed. Returns the located boxes and how
    many boxes could not be placed (no calibration for their camera, or an old box format)."""
    result = await db.execute(
        select(Detection, LayerCapture, Layer)
        .join(LayerCapture, Detection.capture_id == LayerCapture.id)
        .join(Layer, LayerCapture.layer_id == Layer.id)
        .where(Layer.job_id == job.id, Detection.has_defect.is_(True))
        .order_by(Layer.layer_number, Detection.id)
    )
    rows = result.all()
    camera_ids = {capture.camera_id for _, capture, _ in rows}
    calibrations = _CalibrationHistory(
        list((await db.execute(select(CameraCalibration).where(CameraCalibration.camera_id.in_(camera_ids)))).scalars())
        if camera_ids
        else []
    )
    objects = (job.geometry or {}).get("objects") or []

    located, skipped = [], 0
    for detection, capture, layer in rows:
        calibration = calibrations.for_capture(capture.camera_id, capture.captured_at)
        snapshot = layer.telemetry or {}
        frame = (detection.raw_output or {}).get("frame")
        for box_index, box_entry in enumerate((detection.raw_output or {}).get("detections", [])):
            box = full_frame_box(box_entry.get("box") or [], frame)
            if box is None or calibration is None:
                skipped += 1
                continue
            row, model = calibration
            z = float(layer.z_height)
            # The bed's own speed (Y) when known; the head's total speed is an upper bound for it.
            speed = snapshot.get("velocity_y")
            speed = abs(speed) if speed is not None else snapshot.get("velocity")
            location = bed_map.locate(
                model,
                (box[0] + box[2]) / 2,
                (box[1] + box[3]) / 2,
                z=z,
                toolhead_y=snapshot.get("y"),
                speed=speed,
            )
            located.append(
                {
                    "detection_id": detection.id,
                    "box_index": box_index,
                    "capture_id": capture.id,
                    "camera_id": capture.camera_id,
                    "calibration_id": row.id,
                    "calibration_after_capture": row.created_at > capture.captured_at,
                    "layer_number": layer.layer_number,
                    "z": z,
                    "class_name": box_entry.get("class"),
                    "confidence": box_entry.get("confidence"),
                    "box": [round(value, 4) for value in box],
                    "x": location.x,
                    "y": location.y,
                    "uncertainty_mm": location.uncertainty_mm,
                    "reliable": location.reliable,
                    "parallax_mm": location.parallax_mm,
                    "shift_mm": location.shift_mm,
                    "object": object_at(objects, location.x, location.y, location.uncertainty_mm),
                    "head": {key: snapshot.get(key) for key in ("x", "y", "z")},
                    "current_object": snapshot.get("current_object"),
                }
            )
    return located, skipped


async def job_head_path(db: AsyncSession, job_id: int) -> list[list[float]]:
    """The toolhead's XY path during the job, from the 1 Hz telemetry, thinned for drawing."""
    result = await db.execute(
        select(TelemetrySample.x, TelemetrySample.y)
        .where(TelemetrySample.print_job_id == job_id, TelemetrySample.x.is_not(None))
        .order_by(TelemetrySample.ts)
    )
    points = [[round(x, 1), round(y, 1)] for x, y in result.all()]
    step = max(1, math.ceil(len(points) / _MAX_PATH_POINTS))
    return points[::step]


def heatmap_grid(points: list[tuple[float, float]], width: float, depth: float, cell_mm: float) -> list[list[int]]:
    """Counts per cell (rows from the front of the bed, columns from the left)."""
    columns, rows = max(1, math.ceil(width / cell_mm)), max(1, math.ceil(depth / cell_mm))
    grid = [[0] * columns for _ in range(rows)]
    for x, y in points:
        if 0 <= x < width and 0 <= y < depth:
            grid[int(y // cell_mm)][int(x // cell_mm)] += 1
    return grid


async def printer_geometry(db: AsyncSession, printer_id: int) -> dict | None:
    """The bed as last reported live by the listener, else as stored with the latest job."""
    live = latest_geometry.get(printer_id)
    if live and live.get("axis_maximum"):
        return live
    return await db.scalar(
        select(PrintJob.geometry)
        .where(PrintJob.printer_id == printer_id, PrintJob.geometry.is_not(None))
        .order_by(PrintJob.id.desc())
        .limit(1)
    )


async def printer_heatmap(db: AsyncSession, printer_id: int, cell_mm: float, classes: set[str] | None) -> dict:
    """Where on the bed this printer's defects concentrate, over all its jobs. Only locations
    marked reliable are counted; the rest are reported as a number."""
    jobs = (await db.execute(select(PrintJob).where(PrintJob.printer_id == printer_id).order_by(PrintJob.id))).scalars().all()
    points: list[tuple[float, float]] = []
    unreliable = skipped = 0
    for job in jobs:
        located, job_skipped = await locate_job_defects(db, job)
        skipped += job_skipped
        for defect in located:
            if classes and defect["class_name"] not in classes:
                continue
            if defect["reliable"]:
                points.append((defect["x"], defect["y"]))
            else:
                unreliable += 1

    geometry = await printer_geometry(db, printer_id)
    width, depth = bed_dimensions(geometry)
    return {
        "printer_id": printer_id,
        "cell_mm": cell_mm,
        "width_mm": width,
        "depth_mm": depth,
        "counts": heatmap_grid(points, width, depth, cell_mm),
        "jobs": len(jobs),
        "located": len(points),
        "unreliable": unreliable,
        "skipped_boxes": skipped,
        "bed_mesh": (geometry or {}).get("bed_mesh"),
    }
