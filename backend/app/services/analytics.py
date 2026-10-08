"""Figures across print jobs for the analytics page: outcomes, defects by class, interventions by
origin and, from the telemetry, how steady the temperatures held and how much filament went in.
Everything is computed with a handful of grouped queries, not one query per job."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Detection, JobStatus, Layer, LayerCapture, PrinterEvent, PrintJob, TelemetrySample

# Event types that are someone acting on the print (see app/integrations/moonraker/interventions.py).
INTERVENTION_TYPES = (
    "target_changed",
    "speed_factor_changed",
    "flow_factor_changed",
    "fan_changed",
    "z_offset_changed",
    "object_excluded",
)
# Classes the web treats as informational (low precision, no alerts): not counted as defects.
INFORMATIONAL_CLASSES = {"blob_over_extrusion"}


def _duration_seconds(job: PrintJob, now: datetime) -> float:
    return ((job.ended_at or now) - job.started_at).total_seconds()


async def analytics_summary(db: AsyncSession, printer_id: int | None, since: datetime | None, now: datetime) -> dict:
    job_filter = []
    if printer_id is not None:
        job_filter.append(PrintJob.printer_id == printer_id)
    if since is not None:
        job_filter.append(PrintJob.started_at >= since)
    jobs = list((await db.execute(select(PrintJob).where(*job_filter).order_by(PrintJob.started_at))).scalars())
    job_ids = [job.id for job in jobs]
    if not job_ids:
        return {
            "totals": {"jobs": 0},
            "status_counts": {},
            "defects_by_class": {},
            "interventions_by_origin": {},
            "jobs": [],
        }

    layer_counts = dict(
        (await db.execute(select(Layer.job_id, func.count()).where(Layer.job_id.in_(job_ids)).group_by(Layer.job_id))).all()
    )

    # One row per (layer, detection with a defect): a layer counts once per class, whatever the
    # number of cameras or boxes that saw it.
    defect_rows = await db.execute(
        select(Layer.job_id, Layer.id, Detection.defect_classes)
        .join(LayerCapture, LayerCapture.layer_id == Layer.id)
        .join(Detection, Detection.capture_id == LayerCapture.id)
        .where(Layer.job_id.in_(job_ids), Detection.has_defect.is_(True))
    )
    layer_classes: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for job_id, layer_id, classes in defect_rows.all():
        layer_classes[job_id][layer_id].update(name for name in (classes or []) if name not in INFORMATIONAL_CLASSES)

    event_rows = await db.execute(
        select(PrinterEvent.print_job_id, PrinterEvent.origin, func.count())
        .where(PrinterEvent.print_job_id.in_(job_ids), PrinterEvent.event_type.in_(INTERVENTION_TYPES))
        .group_by(PrinterEvent.print_job_id, PrinterEvent.origin)
    )
    interventions: dict[int, dict[str, int]] = defaultdict(dict)
    for job_id, origin, count in event_rows.all():
        interventions[job_id][origin] = count

    # Steady-state temperature error: only while printing layers (not while heating up).
    printing = and_(TelemetrySample.layer_number >= 1)
    nozzle_error = func.abs(TelemetrySample.extruder_temp - TelemetrySample.extruder_target)
    bed_error = func.abs(TelemetrySample.bed_temp - TelemetrySample.bed_target)
    telemetry_rows = await db.execute(
        select(
            TelemetrySample.print_job_id,
            func.avg(nozzle_error).filter(printing, TelemetrySample.extruder_target > 0),
            func.max(nozzle_error).filter(printing, TelemetrySample.extruder_target > 0),
            func.avg(bed_error).filter(printing, TelemetrySample.bed_target > 0),
            func.max(TelemetrySample.filament_used),
            func.count(),
        )
        .where(TelemetrySample.print_job_id.in_(job_ids))
        .group_by(TelemetrySample.print_job_id)
    )
    telemetry = {row[0]: row[1:] for row in telemetry_rows.all()}

    status_counts: dict[str, int] = defaultdict(int)
    defects_by_class: dict[str, int] = defaultdict(int)
    origins: dict[str, int] = defaultdict(int)
    rows = []
    for job in jobs:
        status_counts[job.status.value] += 1
        per_layer = layer_classes.get(job.id, {})
        defective_layers = sum(1 for classes in per_layer.values() if classes)
        classes_count: dict[str, int] = defaultdict(int)
        for classes in per_layer.values():
            for name in classes:
                classes_count[name] += 1
                defects_by_class[name] += 1
        for origin, count in interventions.get(job.id, {}).items():
            origins[origin] += count
        nozzle_mean, nozzle_max, bed_mean, filament, samples = telemetry.get(job.id, (None, None, None, None, 0))
        layers = layer_counts.get(job.id, 0)
        rows.append(
            {
                "id": job.id,
                "printer_id": job.printer_id,
                "file_name": job.file_name,
                "status": job.status.value,
                "started_at": job.started_at,
                "ended_at": job.ended_at,
                "duration_s": round(_duration_seconds(job, now), 1),
                "layers": layers,
                "layers_with_defect": defective_layers,
                "defect_rate": round(defective_layers / layers, 4) if layers else None,
                "classes": dict(classes_count),
                "interventions": interventions.get(job.id, {}),
                "telemetry_samples": samples,
                "nozzle_error_mean_c": None if nozzle_mean is None else round(float(nozzle_mean), 2),
                "nozzle_error_max_c": None if nozzle_max is None else round(float(nozzle_max), 2),
                "bed_error_mean_c": None if bed_mean is None else round(float(bed_mean), 2),
                "filament_m": None if filament is None else round(float(filament) / 1000, 2),
            }
        )

    finished = sum(status_counts.get(status.value, 0) for status in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled))
    total_layers = sum(row["layers"] for row in rows)
    defective = sum(row["layers_with_defect"] for row in rows)
    return {
        "totals": {
            "jobs": len(rows),
            "success_rate": round(status_counts.get(JobStatus.completed.value, 0) / finished, 4) if finished else None,
            "print_hours": round(sum(row["duration_s"] for row in rows) / 3600, 2),
            "layers": total_layers,
            "layers_with_defect": defective,
            "defect_rate": round(defective / total_layers, 4) if total_layers else None,
            "interventions": sum(origins.values()),
            "filament_m": round(sum(row["filament_m"] or 0 for row in rows), 2),
        },
        "status_counts": dict(status_counts),
        "defects_by_class": dict(defects_by_class),
        "interventions_by_origin": dict(origins),
        "jobs": rows,
    }
