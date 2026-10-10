"""Combined confidence for each defect box: the model's confidence, raised when the printer's
telemetry while that layer was printed shows a known cause of that kind of defect (a cold nozzle
for under-extrusion, a bed that lost temperature for warping...).

Nothing else uses it: alerts and the auto-pause still look at the model alone. It is shown next to
each detection so the team can judge it against real prints before deciding whether it should
weigh in on alerts.

How it combines (noisy-OR): score = 1 - (1 - confidence) * product(1 - weight of each signal met).
Telemetry can only raise the score, never lower it: many causes (a partial clog, a wet spool) leave
no trace in the sensors, so normal readings are not evidence against the model."""

import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Detection, Layer, LayerCapture, PrintJob, TelemetrySample

# Klipper's verify_heater "hysteresis" (default 5 °C): the band around the target that Klipper
# itself considers "in range". Further than that, the heater is not holding its temperature.
TEMPERATURE_BAND_C = 5.0
# Slicers calibrate flow in coarse steps of 5 % (OrcaSlicer's flow-rate test, first pass): a
# change of that size is the smallest one meant to change how much plastic comes out.
FLOW_STEP = 0.05
# PWM at 95 % or more: the heater has no headroom left to hold the target.
SATURATED_POWER = 0.95
SATURATED_SECONDS = 5  # at least 5 samples (1 per second) at that power during the layer
# The window is the layer just printed (the one the photo shows on top); if it has fewer samples
# than this, earlier layers are added, so a few seconds of sensor noise or one PID swing (a few
# seconds long) don't decide the outcome.
MIN_WINDOW_SAMPLES = 10
MAX_WINDOW_LAYERS = 3

STRONG, MEDIUM, WEAK = 0.6, 0.3, 0.15


@dataclass(frozen=True)
class SignalSpec:
    key: str
    label: str
    unit: str
    threshold: float
    weight: float
    rationale: str


SIGNALS: dict[str, SignalSpec] = {
    spec.key: spec
    for spec in (
        SignalSpec(
            "no_filament", "Sensor de filamento sin filamento", "", 1, STRONG,
            "Sin filamento no sale plástico.",
        ),
        SignalSpec(
            "heater_saturated", "Calentador de la boquilla al máximo", "s", SATURATED_SECONDS, MEDIUM,
            "Con el calentador al 95 % o más, la boquilla no da abasto para fundir el plástico que se le pide.",
        ),
        SignalSpec(
            "nozzle_cold", "Boquilla por debajo del objetivo", "°C", TEMPERATURE_BAND_C, MEDIUM,
            "Más fría que el objetivo, el plástico fluye peor. 5 °C es la banda que Klipper considera en rango.",
        ),
        SignalSpec(
            "nozzle_hot", "Boquilla por encima del objetivo", "°C", TEMPERATURE_BAND_C, MEDIUM,
            "Más caliente que el objetivo, el plástico gotea más. 5 °C es la banda que Klipper considera en rango.",
        ),
        SignalSpec(
            "nozzle_raised", "Temperatura de boquilla subida durante la impresión", "°C", TEMPERATURE_BAND_C, WEAK,
            "Más caliente que en la primera capa (que suele ser la más caliente): más goteo.",
        ),
        SignalSpec(
            "flow_low", "Flujo reducido", "%", round(100 * (1 - FLOW_STEP), 2), MEDIUM,
            "El factor de flujo (M221) reduce el plástico en la misma proporción. 5 % es el paso de calibración de flujo.",
        ),
        SignalSpec(
            "flow_high", "Flujo aumentado", "%", round(100 * (1 + FLOW_STEP), 2), MEDIUM,
            "El factor de flujo (M221) aumenta el plástico en la misma proporción. 5 % es el paso de calibración de flujo.",
        ),
        SignalSpec(
            "speed_high", "Más rápido de lo laminado", "%", 100, WEAK,
            "El laminador planeó el caudal para el 100 %; por encima se le pide más a la boquilla y a los motores.",
        ),
        SignalSpec(
            "bed_cold", "Cama por debajo del objetivo", "°C", TEMPERATURE_BAND_C, MEDIUM,
            "Con la cama más fría la pieza se adhiere menos y se contrae más. 5 °C es la banda que Klipper considera en rango.",
        ),
        SignalSpec(
            "bed_lowered", "Cama bajada o apagada durante la impresión", "°C", TEMPERATURE_BAND_C, MEDIUM,
            "Bajar la cama respecto de la primera capa enfría la base de la pieza.",
        ),
    )
}

# Which signals bear on each class. Spaghetti has none: it follows a part coming loose or a
# collapse, which the sensors don't see.
CLASS_SIGNALS: dict[str, list[str]] = {
    "under_extrusion": ["no_filament", "heater_saturated", "nozzle_cold", "flow_low", "speed_high"],
    "blob_over_extrusion": ["flow_high", "nozzle_hot"],
    "stringing": ["nozzle_hot", "nozzle_raised"],
    "warping": ["bed_cold", "bed_lowered"],
    "layer_shift": ["speed_high"],
    "spaghetti": [],
}

FORMULA = "puntaje = 1 - (1 - confianza del modelo) x producto de (1 - peso) de cada señal cumplida"


def method() -> dict:
    """What the web shows under "cómo se calcula"."""
    return {
        "formula": FORMULA,
        "window": (
            "Muestras de telemetría (1 por segundo) de la capa recién impresa, la que se ve arriba en la foto; "
            f"si son menos de {MIN_WINDOW_SAMPLES}, se agregan las capas anteriores (hasta {MAX_WINDOW_LAYERS})."
        ),
        "weights": {"fuerte": STRONG, "media": MEDIUM, "debil": WEAK},
        "calibrated": False,
        "signals": [
            {
                "key": spec.key,
                "label": spec.label,
                "unit": spec.unit,
                "operator": _READINGS[spec.key][1],
                "threshold": spec.threshold,
                "weight": spec.weight,
                "rationale": spec.rationale,
                "classes": [name for name, keys in CLASS_SIGNALS.items() if spec.key in keys],
            }
            for spec in SIGNALS.values()
        ],
    }


def _mean(values: list[float]) -> float | None:
    return fmean(values) if values else None


def active_filament_sensors(samples: list[dict]) -> set[str]:
    """Filament sensors that were detecting filament at some point in the job. The Creality Hi
    exposes five (the toolhead's, one more and three for the CFS box slots); the box ones read "no
    filament" the whole time when no box is attached, so only a sensor that has seen filament in
    this job can say it ran out."""
    return {
        key
        for sample in samples
        for key, value in (sample.get("extra") or {}).items()
        if key.endswith(".filament_detected") and value is True
    }


def window_stats(samples: list[dict], active_sensors: set[str] | None = None) -> dict:
    """What the signals look at, from the samples of the window (dicts with the telemetry
    columns). A value is None when the window has no data for it. active_sensors: see
    active_filament_sensors; None means every sensor that reports counts."""
    nozzle = [s["extruder_target"] - s["extruder_temp"] for s in samples
              if s.get("extruder_target") and s.get("extruder_temp") is not None]
    bed = [s["bed_target"] - s["bed_temp"] for s in samples if s.get("bed_target") and s.get("bed_temp") is not None]
    powers = [s["extruder_power"] for s in samples if s.get("extruder_power") is not None]
    flows = [s["extrude_factor"] for s in samples if s.get("extrude_factor") is not None]
    speeds = [s["speed_factor"] for s in samples if s.get("speed_factor") is not None]
    nozzle_targets = [s["extruder_target"] for s in samples if s.get("extruder_target") is not None]
    bed_targets = [s["bed_target"] for s in samples if s.get("bed_target") is not None]
    filament = [value for s in samples for key, value in (s.get("extra") or {}).items()
                if key.endswith(".filament_detected") and isinstance(value, bool)
                and (active_sensors is None or key in active_sensors)]
    return {
        "samples": len(samples),
        "nozzle_deficit": _mean(nozzle),
        "bed_deficit": _mean(bed),
        "saturated_seconds": sum(1 for power in powers if power >= SATURATED_POWER) if powers else None,
        "min_flow": min(flows) if flows else None,
        "max_flow": max(flows) if flows else None,
        "max_speed": max(speeds) if speeds else None,
        "max_nozzle_target": max(nozzle_targets) if nozzle_targets else None,
        "min_bed_target": min(bed_targets) if bed_targets else None,
        "filament_out": (not all(filament)) if filament else None,
    }


def _difference(minuend: float | None, subtrahend: float | None) -> float | None:
    return None if minuend is None or subtrahend is None else minuend - subtrahend


def _percent(factor: float | None) -> float | None:
    return None if factor is None else 100 * factor


# Each signal's value in the window (None: no data) and how it is compared with its threshold.
_READINGS = {
    "no_filament": (lambda stats, initial: None if stats["filament_out"] is None else float(stats["filament_out"]), ">="),
    "heater_saturated": (lambda stats, initial: stats["saturated_seconds"], ">="),
    "nozzle_cold": (lambda stats, initial: stats["nozzle_deficit"], ">"),
    "nozzle_hot": (lambda stats, initial: None if stats["nozzle_deficit"] is None else -stats["nozzle_deficit"], ">"),
    "nozzle_raised": (lambda stats, initial: _difference(stats["max_nozzle_target"], initial.get("nozzle_target") or None), ">="),
    "flow_low": (lambda stats, initial: _percent(stats["min_flow"]), "<="),
    "flow_high": (lambda stats, initial: _percent(stats["max_flow"]), ">="),
    "speed_high": (lambda stats, initial: _percent(stats["max_speed"]), ">"),
    "bed_cold": (lambda stats, initial: stats["bed_deficit"], ">"),
    "bed_lowered": (lambda stats, initial: _difference(initial.get("bed_target") or None, stats["min_bed_target"]), ">="),
}
_COMPARE = {">": float.__gt__, ">=": float.__ge__, "<=": float.__le__}


def _signal(key: str, stats: dict, initial: dict) -> dict:
    """One signal's reading: its value in the window, the threshold and whether it was met."""
    spec = SIGNALS[key]
    read, operator = _READINGS[key]
    value = read(stats, initial)
    # Rounded before comparing: REAL columns store 1.05 as 1.0499999523.
    value = None if value is None else round(float(value), 2)
    return {
        "key": key,
        "label": spec.label,
        "unit": spec.unit,
        "operator": operator,
        "threshold": spec.threshold,
        "weight": spec.weight,
        "value": value,
        "met": value is not None and _COMPARE[operator](value, float(spec.threshold)),
    }


def evaluate(class_name: str | None, confidence: float | None, stats: dict, initial: dict) -> dict:
    """The combined score of one box and the readings behind it."""
    signals = [_signal(key, stats, initial) for key in CLASS_SIGNALS.get(class_name or "", [])]
    base = float(confidence or 0.0)
    remaining = 1.0 - base
    for signal in signals:
        if signal["met"]:
            remaining *= 1.0 - signal["weight"]
    return {"score": round(1.0 - remaining, 3), "signals": signals}


def initial_targets(samples: list[dict]) -> dict:
    """Nozzle and bed targets of the first layer, the reference for "raised" and "lowered"."""
    first = [s for s in samples if (s.get("layer_number") or 0) >= 1]
    nozzle = next((s["extruder_target"] for s in first if s.get("extruder_target")), None)
    bed = next((s["bed_target"] for s in first if s.get("bed_target")), None)
    return {"nozzle_target": nozzle, "bed_target": bed}


def layer_window(by_layer: dict[int, list[dict]], layer_number: int) -> tuple[list[dict], list[int]]:
    """The samples of the layer the photo shows (the one before the layer change), plus earlier
    layers while there are too few."""
    window: list[dict] = []
    layers: list[int] = []
    for number in range(layer_number - 1, max(layer_number - 1 - MAX_WINDOW_LAYERS, -1), -1):
        if number in by_layer:
            window = by_layer[number] + window
            layers.insert(0, number)
        if len(window) >= MIN_WINDOW_SAMPLES:
            break
    return window, layers


_SAMPLE_COLUMNS = (
    "ts", "layer_number", "extruder_temp", "extruder_target", "extruder_power", "bed_temp", "bed_target",
    "extrude_factor", "speed_factor", "extra",
)


async def job_fusion(db: AsyncSession, job: PrintJob) -> list[dict]:
    """The combined score of every defect box of the job, in layer order."""
    rows = (
        await db.execute(
            select(Detection, Layer)
            .join(LayerCapture, Detection.capture_id == LayerCapture.id)
            .join(Layer, LayerCapture.layer_id == Layer.id)
            .where(Layer.job_id == job.id, Detection.has_defect.is_(True))
            .order_by(Layer.layer_number, Detection.id)
        )
    ).all()
    if not rows:
        return []

    columns = [getattr(TelemetrySample, name) for name in _SAMPLE_COLUMNS]
    result = await db.execute(select(*columns).where(TelemetrySample.print_job_id == job.id).order_by(TelemetrySample.ts))
    samples = [dict(zip(_SAMPLE_COLUMNS, row)) for row in result.all()]
    by_layer: dict[int, list[dict]] = defaultdict(list)
    for sample in samples:
        if sample["layer_number"] is not None:
            by_layer[sample["layer_number"]].append(sample)
    initial = initial_targets(samples)
    active_sensors = active_filament_sensors(samples)

    items = []
    for detection, layer in rows:
        window, layers = layer_window(by_layer, layer.layer_number)
        source = "telemetry"
        if not window and layer.telemetry:
            # Jobs from before the 1 Hz telemetry, or a gap: the snapshot taken at the layer change.
            window, source = [layer.telemetry], "layer_snapshot"
        stats = window_stats(window, active_sensors)
        for index, box in enumerate((detection.raw_output or {}).get("detections", [])):
            confidence = box.get("confidence")
            outcome = evaluate(box.get("class"), confidence, stats, initial)
            items.append(
                {
                    "detection_id": detection.id,
                    "box_index": index,
                    "layer_number": layer.layer_number,
                    "class_name": box.get("class"),
                    "confidence": None if confidence is None or math.isnan(confidence) else round(float(confidence), 3),
                    "score": outcome["score"],
                    "signals": outcome["signals"],
                    "window": {"source": source if window else None, "samples": len(window), "layers": layers},
                }
            )
    return items
