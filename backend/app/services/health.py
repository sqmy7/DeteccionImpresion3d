"""Printer health from the telemetry of its past jobs: is a heater needing more power to hold its
temperature than it used to (wear, a loose heater cartridge, a damaged sock or a draught), holding
it less steadily, or heating up more slowly?

Per job and heater it measures, once the temperature has settled on its target:
  - hold power: mean PWM needed to keep the target,
  - oscillation: standard deviation of temperature - target,
  - largest excursion: the biggest |temperature - target|,
and, from the heat-up at the start, the heating rate.

Each job is then compared with the printer's own past (a control chart): a baseline from its first
jobs at the same target, with limits at mean +- 3 standard deviations (Shewhart) and the Western
Electric rules for trends. Nothing here comes from a spec sheet: "normal" is what this printer did
before. The thresholds that are absolute come from Klipper itself (see the constants)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import fmean, pstdev

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobStatus, PrintJob, TelemetrySample

# Klipper's PID_SETTLE_DELTA: M109 / TEMPERATURE_WAIT consider the heater settled within 1 °C.
SETTLE_DELTA_C = 1.0
# Klipper's verify_heater "hysteresis" (default 5 °C): the band Klipper considers "in range".
IN_RANGE_C = 5.0
# At least 30 one-second samples settled on the target before a mean or a deviation is reported,
# so a single PID swing (a few seconds) doesn't decide it.
MIN_STEADY_SAMPLES = 30
# Heating rate: time to go from 20 % to 80 % of the way between a nominal room temperature and the
# target (fixed temperatures for a given target, so heat-ups at the same target compare), where the
# rate is roughly steady (the start lags and the end slows down near the target). Only heat-ups
# that start cold enough to cross both points and at least 30 °C below the target are measured.
NOMINAL_ROOM_C = 25.0
MIN_HEATUP_C = 30.0
HEATUP_FROM, HEATUP_TO = 0.2, 0.8
# Targets within 5 °C are compared with each other: holding 240 °C takes more power than 200 °C.
TARGET_BUCKET_C = 5.0
# Control chart: baseline from the first jobs at that target (at least 5, at most 10).
MIN_BASELINE_JOBS = 5
MAX_BASELINE_JOBS = 10
# Resolution of the stored values; a baseline that varies less than this is treated as varying
# this much, so identical jobs don't make every tiny difference an anomaly.
RESOLUTION = {"hold_power": 0.001, "oscillation": 0.01, "max_excursion": 0.01, "heating_rate": 0.01}
MAX_JOBS = 100  # most recent finished jobs analyzed per printer
# The sampler writes in batches of 10: a job closed less than this ago may still get samples.
_SETTLED_AFTER_END = timedelta(seconds=60)

HEATERS = {
    "extruder": ("Boquilla", "extruder_temp", "extruder_target", "extruder_power"),
    "bed": ("Cama", "bed_temp", "bed_target", "bed_power"),
}


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str
    worse: str  # "up" or "down": which direction is a problem
    description: str


METRICS = [
    MetricSpec("hold_power", "Potencia para mantener la temperatura", "%", "up",
               "Promedio del PWM del calentador una vez asentado en el objetivo. Si sube con el tiempo a igual objetivo, el "
               "calentador rinde menos o pierde más calor (desgaste, cartucho flojo, funda dañada, corriente de aire)."),
    MetricSpec("oscillation", "Oscilación", "°C", "up",
               "Desviación estándar de temperatura - objetivo una vez asentada. Si crece, el control oscila más (PID desajustado, "
               "termistor flojo, ventilador que golpea el bloque)."),
    MetricSpec("max_excursion", "Mayor desviación", "°C", "up",
               "La mayor diferencia con el objetivo una vez asentada. Por encima de 5 °C sale de la banda que Klipper considera en rango."),
    MetricSpec("heating_rate", "Velocidad de calentamiento", "°C/s", "down",
               "Grados por segundo entre el 20 % y el 80 % del camino de 25 °C al objetivo, en los arranques en frío. Si baja a "
               "igual objetivo, el calentador entrega menos potencia."),
]


def _bucket(target: float) -> float:
    return round(target / TARGET_BUCKET_C) * TARGET_BUCKET_C


def _crossing_time(samples: list[tuple[float, float]], level: float) -> float | None:
    """First time (seconds) the series (t, temperature) reaches `level` going up, interpolated."""
    for (t0, v0), (t1, v1) in zip(samples, samples[1:]):
        if v0 < level <= v1:
            return t0 + (t1 - t0) * (level - v0) / (v1 - v0)
    return None


def heater_metrics(rows: list[dict], temp_key: str, target_key: str, power_key: str) -> dict | None:
    """The job's figures for one heater (rows ordered by time, with "t" in seconds and
    "printing" = a layer had started). None when the heater was never on."""
    steady: dict[float, dict[str, list[float]]] = defaultdict(lambda: {"dev": [], "power": []})
    heating_rate = heating_target = None
    target = None
    settled = False
    heat_start: tuple[float, float, int] | None = None  # (start temperature, target, index)
    for index, row in enumerate(rows):
        temp, new_target, power = row.get(temp_key), row.get(target_key), row.get(power_key)
        if temp is None or new_target is None:
            continue
        if new_target != target:
            target, settled = new_target, False
            heat_start = (temp, new_target, index) if new_target > 0 and new_target - temp >= MIN_HEATUP_C else None
        if not target:
            continue
        deviation = temp - target
        if not settled and abs(deviation) <= SETTLE_DELTA_C:
            settled = True
            if heat_start is not None and heating_rate is None:
                start_temp, heat_target, start_index = heat_start
                low = NOMINAL_ROOM_C + HEATUP_FROM * (heat_target - NOMINAL_ROOM_C)
                high = NOMINAL_ROOM_C + HEATUP_TO * (heat_target - NOMINAL_ROOM_C)
                series = [(r["t"], r[temp_key]) for r in rows[start_index:index + 1] if r.get(temp_key) is not None]
                t_low, t_high = _crossing_time(series, low), _crossing_time(series, high)
                if start_temp < low and t_low is not None and t_high is not None and t_high > t_low:
                    heating_rate, heating_target = (high - low) / (t_high - t_low), heat_target
            heat_start = None
        if settled and row["printing"]:
            steady[target]["dev"].append(deviation)
            if power is not None:
                steady[target]["power"].append(power)

    if target is None and heating_rate is None:
        return None
    usable = {key: values for key, values in steady.items() if len(values["dev"]) >= MIN_STEADY_SAMPLES}
    if not usable and heating_rate is None:
        return None
    result = {"target": None, "steady_seconds": 0, "hold_power": None, "oscillation": None, "max_excursion": None,
              "heating_rate": None if heating_rate is None else round(heating_rate, 3), "heating_target": heating_target}
    if usable:
        # The target it spent the most time on (a print may change it, e.g. after the first layer).
        main_target, values = max(usable.items(), key=lambda item: len(item[1]["dev"]))
        result.update(
            target=main_target,
            steady_seconds=len(values["dev"]),
            hold_power=round(fmean(values["power"]), 4) if len(values["power"]) >= MIN_STEADY_SAMPLES else None,
            oscillation=round(pstdev(values["dev"]), 3),
            max_excursion=round(max(abs(value) for value in values["dev"]), 2),
        )
    return result


def job_metrics(samples: list[dict]) -> dict:
    """Both heaters' figures for one job, from its samples (dicts ordered by ts)."""
    if not samples:
        return {name: None for name in HEATERS}
    start: datetime = samples[0]["ts"]
    rows = [
        {**sample, "t": (sample["ts"] - start).total_seconds(), "printing": (sample.get("layer_number") or 0) >= 1}
        for sample in samples
    ]
    return {name: heater_metrics(rows, temp_key, target_key, power_key)
            for name, (_, temp_key, target_key, power_key) in HEATERS.items()}


def control_chart(values: list[float], worse: str, resolution: float) -> dict:
    """Baseline, limits and findings for a chronological series (one value per job)."""
    if len(values) < MIN_BASELINE_JOBS + 1:
        return {"status": "insufficient", "baseline": None, "flags": [], "findings": []}
    # The first jobs, leaving at least the last three out of it when there are enough, so a recent
    # change doesn't hide inside its own baseline.
    baseline_size = max(MIN_BASELINE_JOBS, min(MAX_BASELINE_JOBS, len(values) - 3))
    baseline = values[:baseline_size]
    mean = fmean(baseline)
    std = max(pstdev(baseline), resolution)
    sign = 1 if worse == "up" else -1
    upper, lower = mean + 3 * std, mean - 3 * std

    # z of each point in the "worse" direction (positive = worse).
    z = [sign * (value - mean) / std for value in values]
    flags: list[list[str]] = [[] for _ in values]
    findings: list[str] = []
    for index in range(baseline_size, len(values)):
        if z[index] > 3:
            flags[index].append("beyond_3sigma")
        recent = z[max(baseline_size, index - 2):index + 1]
        if len(recent) == 3 and sum(1 for value in recent if value > 2) >= 2:
            flags[index].append("two_of_three_beyond_2sigma")
        run = z[max(baseline_size, index - 7):index + 1]
        if len(run) == 8 and all(value > 0 for value in run):
            flags[index].append("eight_on_worse_side")

    last = flags[-1]
    if "beyond_3sigma" in last:
        findings.append("El último trabajo quedó fuera del límite de control (3 desviaciones estándar de la línea base).")
    if "two_of_three_beyond_2sigma" in last:
        findings.append("Dos de los últimos tres trabajos pasaron 2 desviaciones estándar hacia el lado malo.")
    if "eight_on_worse_side" in last:
        findings.append("Los últimos ocho trabajos quedaron todos del lado malo del promedio: deriva sostenida.")
    return {
        "status": "attention" if last else "normal",
        "baseline": {"n": baseline_size, "mean": round(mean, 4), "std": round(std, 4),
                     "upper": round(upper, 4), "lower": round(lower, 4)},
        "flags": flags,
        "findings": findings,
    }


def method() -> dict:
    return {
        "settle_delta_c": SETTLE_DELTA_C,
        "in_range_c": IN_RANGE_C,
        "min_steady_samples": MIN_STEADY_SAMPLES,
        "min_heatup_c": MIN_HEATUP_C,
        "target_bucket_c": TARGET_BUCKET_C,
        "min_baseline_jobs": MIN_BASELINE_JOBS,
        "max_baseline_jobs": MAX_BASELINE_JOBS,
        "metrics": [{"key": spec.key, "label": spec.label, "unit": spec.unit, "worse": spec.worse,
                     "description": spec.description} for spec in METRICS],
    }


_COLUMNS = ("ts", "layer_number", "extruder_temp", "extruder_target", "extruder_power", "bed_temp", "bed_target", "bed_power")
# Finished jobs never change: their figures are computed once per backend process. Keyed with the
# start time too, since a database rebuilt from scratch reuses job ids.
_cache: dict[tuple[int, datetime], dict] = {}


async def _metrics_for(db: AsyncSession, job: PrintJob) -> dict:
    key = (job.id, job.started_at)
    if key in _cache:
        return _cache[key]
    columns = [getattr(TelemetrySample, name) for name in _COLUMNS]
    result = await db.execute(select(*columns).where(TelemetrySample.print_job_id == job.id).order_by(TelemetrySample.ts))
    metrics = job_metrics([dict(zip(_COLUMNS, row)) for row in result.all()])
    if job.status != JobStatus.running and job.ended_at and datetime.now(timezone.utc) - job.ended_at > _SETTLED_AFTER_END:
        _cache[key] = metrics
    return metrics


async def printer_health(db: AsyncSession, printer_id: int) -> dict:
    """Control charts of every heater metric for the printer's finished jobs."""
    jobs = list(
        (
            await db.execute(
                select(PrintJob)
                .where(PrintJob.printer_id == printer_id, PrintJob.status != JobStatus.running)
                .order_by(PrintJob.started_at.desc())
                .limit(MAX_JOBS)
            )
        ).scalars()
    )
    jobs.reverse()
    per_job = [(job, await _metrics_for(db, job)) for job in jobs]
    with_data = [(job, metrics) for job, metrics in per_job if any(metrics.values())]

    heaters = []
    for name, (label, *_columns) in HEATERS.items():
        entries = [(job, metrics[name]) for job, metrics in with_data if metrics.get(name)]
        latest_target = next((m["target"] for _, m in reversed(entries) if m.get("target") is not None), None)
        bucket = _bucket(latest_target) if latest_target is not None else None
        # Heat-ups compare at the target they heated to (often the first layer's, a bit hotter).
        latest_heating = next((m["heating_target"] for _, m in reversed(entries) if m.get("heating_target") is not None), None)
        heating_bucket = _bucket(latest_heating) if latest_heating is not None else None
        metrics_out = []
        for spec in METRICS:
            target_key, wanted = ("heating_target", heating_bucket) if spec.key == "heating_rate" else ("target", bucket)
            series = [(job, m) for job, m in entries
                      if m.get(spec.key) is not None and m.get(target_key) is not None and _bucket(m[target_key]) == wanted]
            values = [float(m[spec.key]) for _, m in series]
            chart = control_chart(values, spec.worse, RESOLUTION[spec.key])
            absolute = None
            if spec.key == "max_excursion" and values and values[-1] > IN_RANGE_C:
                absolute = (f"En el último trabajo se apartó {values[-1]:.1f} °C del objetivo ya asentado: más de los "
                            f"{IN_RANGE_C:.0f} °C que Klipper considera en rango.")
            status = chart["status"]
            if absolute:
                status = "attention"
            metrics_out.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "unit": spec.unit,
                    "worse": spec.worse,
                    "status": status,
                    "baseline": chart["baseline"],
                    "findings": ([absolute] if absolute else []) + chart["findings"],
                    "points": [
                        {"job_id": job.id, "started_at": job.started_at, "file_name": job.file_name,
                         "value": value, "target": m.get(target_key), "flags": chart["flags"][index] if chart["flags"] else []}
                        for index, ((job, m), value) in enumerate(zip(series, values))
                    ],
                }
            )
        heaters.append({"heater": name, "label": label, "target_bucket": bucket, "metrics": metrics_out})

    return {
        "printer_id": printer_id,
        "jobs_considered": len(jobs),
        "jobs_with_telemetry": len(with_data),
        "heaters": heaters,
        "method": method(),
    }
