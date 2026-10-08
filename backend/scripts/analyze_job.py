"""Analysis of a finished print job from PrintWatch's own database (only SELECTs, writes nothing).

Checks the job closed properly, compares the filament the printer reported with the slicer's weight,
and replays the job to measure how well each remaining-time method (app/services/eta.py) predicted the
real end.

usage (repo root, DATABASE_URL pointing at the database to read):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\analyze_job.py 43 --total-layers 486 \\
        --slicer-seconds 21627 --slicer-grams 201.83 \\
        --running-at 2026-10-08T19:14:03Z=11811.48
"""

import argparse
import asyncio
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Layer, PrintJob, TelemetrySample  # noqa: E402
from app.services import costs, eta, printer_events  # noqa: E402

PETG_DENSITY = 1.27


def moments(points: list[tuple[float, float | None, int | None]], every_s: float) -> list[eta.Reading]:
    chosen, next_at = [], None
    for t, progress, layer in points:
        if next_at is None or t >= next_at:
            chosen.append(eta.Reading(t, progress, layer))
            next_at = t + every_s
    return chosen


def replay(points, end_t: float, total_layers, slicer_seconds, running_at_origin, every_s: float, recent_s: float) -> dict:
    """Predictions of each method at each moment, with the real remaining time."""
    readings = moments(points, every_s)
    first = eta.Reading(*points[0])
    table = []
    for now in readings:
        window = next((r for r in readings if r.t >= now.t - recent_s), None)
        table.append(
            {
                "t": now.t,
                "real": end_t - now.t,
                "progress": eta.by_progress(first, now),
                "layers": eta.by_layers(first, now, total_layers),
                "layers_recent": eta.by_layers(first, now, total_layers, window=window if window and window.t < now.t else None),
                "slicer": eta.by_slicer(slicer_seconds, None if running_at_origin is None else running_at_origin + now.t),
            }
        )
    return {
        "table": table,
        "errors": {
            method: eta.errors([(row["real"], row[method]) for row in table])
            for method in ("progress", "layers", "layers_recent", "slicer")
        },
    }


def minutes(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds / 60:.0f}"


async def main(args) -> None:
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        job = await db.get(PrintJob, args.job_id)
        print(f"# Trabajo {job.id}: {job.file_name}")
        print(f"estado={job.status.value} inicio={job.started_at} fin={job.ended_at}")
        total = await db.scalar(select(func.count()).select_from(TelemetrySample).where(TelemetrySample.print_job_id == job.id))
        layers = (await db.execute(select(func.count(), func.min(Layer.layer_number), func.max(Layer.layer_number)).where(Layer.job_id == job.id))).one()
        print(f"muestras={total} capas={layers[0]} (de {layers[1]} a {layers[2]}) estimadas={job.estimated_layers}")
        chain = await printer_events.verify_chain(db, job.printer_id)
        print(f"cadena de eventos: ok={chain['ok']} eventos={chain['events_checked']} ultimo_hash={chain['last_hash']}")

        rows = (
            await db.execute(
                select(TelemetrySample.ts, TelemetrySample.progress, TelemetrySample.layer_number, TelemetrySample.filament_used)
                .where(TelemetrySample.print_job_id == job.id)
                .order_by(TelemetrySample.ts)
            )
        ).all()
        if not rows:
            return
        origin = rows[0].ts
        points = [((r.ts - origin).total_seconds(), r.progress, r.layer_number) for r in rows]
        gaps = [b[0] - a[0] for a, b in zip(points, points[1:])]
        print(f"muestras: primera {rows[0].ts}, ultima {rows[-1].ts}; huecos de mas de 5 s: {sum(1 for g in gaps if g > 5)} (mayor {max(gaps):.0f} s)")
        used = [r.filament_used for r in rows if r.filament_used is not None]
        used_mm = max(used)

        print("\n## Filamento")
        area = math.pi * (costs.DEFAULTS["filament_diameter_mm"] / 2) ** 2
        density_g = used_mm * area * PETG_DENSITY / 1000
        print(f"print_stats.filament_used final: {used_mm:.0f} mm")
        print(f"densidad del PETG ({PETG_DENSITY} g/cm3, 1,75 mm): {density_g:.1f} g")
        if args.slicer_grams:
            print(f"laminador (filament_used_g): {args.slicer_grams:.2f} g")
            print(f"cociente laminador / densidad: {args.slicer_grams / density_g:.3f}  (gramos por mm del laminador: {args.slicer_grams / used_mm * 1000:.3f} mg/mm)")

        if job.ended_at is None:
            print("\n(el trabajo sigue abierto: sin tabla de tiempo restante)")
            return
        end_t = (job.ended_at - origin).total_seconds()
        running_origin = None
        if args.running_at:
            stamp, value = args.running_at.split("=")
            at = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
            running_origin = float(value) - (at - origin).total_seconds()  # print_duration at the first sample
        result = replay(points, end_t, args.total_layers, args.slicer_seconds, running_origin, args.every_minutes * 60, args.recent_minutes * 60)

        print("\n## Tiempo restante (minutos) en varios instantes")
        print("| minuto | capa | progreso | real | avance | capas | capas recientes | laminador |")
        print("|---|---|---|---|---|---|---|---|")
        by_t = {p[0]: p for p in points}
        for row in result["table"][:: max(1, len(result["table"]) // 14)]:
            _, progress, layer = by_t.get(row["t"], (0, None, None))
            print(f"| {row['t'] / 60:.0f} | {layer} | {'-' if progress is None else f'{progress:.2f}'} | {minutes(row['real'])} | {minutes(row['progress'])} | {minutes(row['layers'])} | {minutes(row['layers_recent'])} | {minutes(row['slicer'])} |")
        print("\n## Error de cada metodo")
        print("| metodo | momentos | error absoluto medio (min) | error con signo (min, + = demasiado) | error relativo medio |")
        print("|---|---|---|---|---|")
        for method, error in result["errors"].items():
            if error is None:
                print(f"| {method} | 0 | - | - | - |")
            else:
                print(f"| {method} | {error['moments']} | {error['mean_abs_error_s'] / 60:.1f} | {error['mean_signed_error_s'] / 60:+.1f} | {error['mean_abs_relative']:.0%} |")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_id", type=int)
    parser.add_argument("--total-layers", type=int)
    parser.add_argument("--slicer-seconds", type=float, help="estimacion total del laminador (del nombre del archivo)")
    parser.add_argument("--slicer-grams", type=float)
    parser.add_argument("--running-at", help="ISO=segundos: print_duration de Klipper en un instante, para ubicar el origen")
    parser.add_argument("--every-minutes", type=float, default=2.0)
    parser.add_argument("--recent-minutes", type=float, default=10.0)
    asyncio.run(main(parser.parse_args()))
