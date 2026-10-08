"""Cost estimate of a print: the filament it used times a price per kg, plus the energy of its two
heaters (their PWM over time times their nominal wattage) times a price per kWh.

It is an estimate on purpose and the web says so: the filament is what the printer commanded to
extrude (print_stats.filament_used), not what was weighed; the energy only counts the heaters (no
motors, fans, electronics or screen) and assumes each heater delivers its nominal power when on;
and the prices are whatever the team configured."""

import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting, PrintJob, TelemetrySample

SETTINGS_KEY = "costs"

# Used until the team saves its own values. The prices are only examples (the web asks to set
# them); the wattages come from the Creality Hi's published figures.
DEFAULTS: dict[str, float | str] = {
    "currency": "COP",
    "filament_price_per_kg": 80000.0,
    "energy_price_per_kwh": 900.0,
    # Hotend heater of the Creality Hi: 50 W (spare-part listing of its hotend assembly).
    "extruder_heater_w": 50.0,
    # Bed: 1000 W AC at 220 V per the spec sheet. A resistive heater's power goes with the square of
    # the voltage, so on 120 V mains (Colombia) it gives ~300 W, consistent with the printer's
    # 390 W rated power at 110 V.
    "bed_heater_w": 300.0,
    "filament_diameter_mm": 1.75,
    # PLA, used when the file gives neither the filament weight nor a known material.
    "default_density_g_cm3": 1.24,
}

# Typical densities (g/cm³) from filament makers' data sheets, by the material the slicer names.
DENSITIES = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PA": 1.14, "PC": 1.20, "HIPS": 1.04, "PVA": 1.23}

# Samples further apart than this are a gap in the series (backend down, printer unreachable):
# the energy of the gap is not guessed.
MAX_GAP_SECONDS = 5.0


async def get_settings(db: AsyncSession) -> dict:
    row = await db.get(AppSetting, SETTINGS_KEY)
    values = {**DEFAULTS, **(row.value if row else {})}
    return {**values, "is_default": row is None, "updated_at": row.updated_at if row else None}


async def save_settings(db: AsyncSession, values: dict, user_id: int | None) -> dict:
    row = await db.get(AppSetting, SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=values, updated_by=user_id)
        db.add(row)
    else:
        row.value = values
        row.updated_by = user_id
        row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_settings(db)


def density_for(material: str | None, default: float) -> tuple[float, str | None]:
    """Density of the named material ("PLA", "PETG-CF", "PLA+"...), else the default."""
    if material:
        name = material.strip().upper()
        for key, density in DENSITIES.items():
            if name.startswith(key):
                return density, key
    return default, None


def filament_grams(used_mm: float, file: dict, settings: dict) -> dict:
    """Grams for a length of filament: with the slicer's own grams per mm when the file has them
    (that already includes its density and diameter), else from the material's density."""
    total_mm, total_g = file.get("filament_total"), file.get("filament_weight_total")
    if isinstance(total_mm, (int, float)) and isinstance(total_g, (int, float)) and total_mm > 0 and total_g > 0:
        return {"grams": used_mm * total_g / total_mm, "method": "slicer", "density": None, "material": file.get("filament_type")}
    density, material = density_for(file.get("filament_type"), float(settings["default_density_g_cm3"]))
    area_mm2 = math.pi * (float(settings["filament_diameter_mm"]) / 2) ** 2
    return {"grams": used_mm * area_mm2 * density / 1000, "method": "density", "density": density,
            "material": material or file.get("filament_type")}


def heater_energy_wh(samples: list[dict], settings: dict) -> dict:
    """Energy of each heater: PWM x nominal watts, integrated over time (rectangles: each sample
    holds until the next one, or 1 s for the last)."""
    watts = {"extruder": float(settings["extruder_heater_w"]), "bed": float(settings["bed_heater_w"])}
    energy = {"extruder": 0.0, "bed": 0.0}
    covered = 0.0
    for current, following in zip(samples, samples[1:] + [None]):
        step = 1.0 if following is None else (following["ts"] - current["ts"]).total_seconds()
        if step <= 0 or step > MAX_GAP_SECONDS:
            continue
        covered += step
        for heater in energy:
            power = current.get(f"{heater}_power")
            if power is not None:
                energy[heater] += max(0.0, min(1.0, power)) * watts[heater] * step / 3600
    return {"extruder_wh": energy["extruder"], "bed_wh": energy["bed"], "covered_seconds": covered}


async def job_cost(db: AsyncSession, job: PrintJob, settings: dict | None = None) -> dict:
    settings = settings or await get_settings(db)
    result = await db.execute(
        select(TelemetrySample.ts, TelemetrySample.extruder_power, TelemetrySample.bed_power, TelemetrySample.filament_used)
        .where(TelemetrySample.print_job_id == job.id)
        .order_by(TelemetrySample.ts)
    )
    samples = [{"ts": ts, "extruder_power": extruder, "bed_power": bed, "filament_used": used} for ts, extruder, bed, used in result.all()]
    file = (job.geometry or {}).get("file") or {}

    used_values = [sample["filament_used"] for sample in samples if sample["filament_used"] is not None]
    used_mm = max(used_values) if used_values else None
    filament = {"used_mm": None, "used_g": None, "method": None, "density": None, "material": file.get("filament_type"), "cost": None}
    if used_mm is not None:
        grams = filament_grams(used_mm, file, settings)
        filament.update(
            used_mm=round(used_mm, 1),
            used_g=round(grams["grams"], 2),
            method=grams["method"],
            density=grams["density"],
            material=grams["material"],
            cost=round(grams["grams"] / 1000 * float(settings["filament_price_per_kg"]), 2),
        )
    filament["estimated_mm"] = file.get("filament_total")
    filament["estimated_g"] = file.get("filament_weight_total")

    energy = None
    if samples:
        wh = heater_energy_wh(samples, settings)
        kwh = (wh["extruder_wh"] + wh["bed_wh"]) / 1000
        energy = {
            "extruder_wh": round(wh["extruder_wh"], 2),
            "bed_wh": round(wh["bed_wh"], 2),
            "total_kwh": round(kwh, 4),
            "covered_seconds": round(wh["covered_seconds"]),
            "cost": round(kwh * float(settings["energy_price_per_kwh"]), 2),
        }

    parts = [part["cost"] for part in (filament, energy) if part and part.get("cost") is not None]
    return {
        "job_id": job.id,
        "currency": settings["currency"],
        "filament": filament,
        "energy": energy,
        "total_cost": round(sum(parts), 2) if parts else None,
        "settings": {key: settings[key] for key in DEFAULTS},
        "settings_are_default": settings["is_default"],
    }
