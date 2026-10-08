"""Printer health: heater figures per job and control charts against the printer's own past."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.api.deps import get_current_user
from app.db.models import IntegrationType, JobStatus, Printer, PrintJob, TelemetrySample, User, UserRole
from app.db.session import get_db
from app.main import app
from app.services import health

START = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _job_samples(start: datetime, hold_power=0.3, noise=0.2, heat_rate=4.0, target=240.0, cold=25.0,
                 printing_from=60, seconds=200) -> list[dict]:
    """A nozzle heating at a constant rate, then held on target with an alternating +-noise and
    a constant power; layers start at `printing_from`."""
    samples, temp = [], cold
    for second in range(seconds):
        heating = temp < target - 0.5
        temp = min(target, temp + heat_rate) if heating else target + noise * (-1) ** second
        samples.append({
            "ts": start + timedelta(seconds=second),
            "layer_number": 0 if second < printing_from else 1 + (second - printing_from) // 10,
            "extruder_temp": temp, "extruder_target": target, "extruder_power": 1.0 if heating else hold_power,
            "bed_temp": None, "bed_target": None, "bed_power": None,
        })
    return samples


def test_heater_figures_of_one_job():
    metrics = health.job_metrics(_job_samples(START))
    extruder = metrics["extruder"]
    assert extruder["target"] == 240.0
    assert extruder["heating_rate"] == pytest.approx(4.0, abs=0.01)  # from 68 to 197 °C (20-80 % of 25-240)
    assert extruder["heating_target"] == 240.0
    assert extruder["hold_power"] == pytest.approx(0.3, abs=1e-6)
    assert extruder["oscillation"] == pytest.approx(0.2, abs=1e-3)
    assert extruder["max_excursion"] == pytest.approx(0.2, abs=1e-3)
    assert extruder["steady_seconds"] == 140  # settled at 54 s, but only printing (from 60 s) counts
    assert metrics["bed"] is None


def test_too_little_settled_time_reports_no_hold_figures():
    extruder = health.job_metrics(_job_samples(START, seconds=80))["extruder"]  # 20 s printing
    assert extruder["hold_power"] is None and extruder["oscillation"] is None
    assert extruder["heating_rate"] == pytest.approx(4.0, abs=0.01)  # the heat-up was complete


def test_warm_start_has_no_heating_rate():
    extruder = health.job_metrics(_job_samples(START, cold=225.0))["extruder"]
    assert extruder["heating_rate"] is None and extruder["hold_power"] is not None


def test_control_chart_needs_a_baseline_then_flags_a_jump():
    base = [0.30, 0.31, 0.29, 0.30, 0.31]
    assert health.control_chart(base, "up", 0.001)["status"] == "insufficient"
    chart = health.control_chart(base + [0.40], "up", 0.001)
    assert chart["status"] == "attention"
    assert chart["flags"][-1] == ["beyond_3sigma"]
    assert chart["baseline"]["n"] == 5 and chart["baseline"]["mean"] == pytest.approx(0.302)
    # A drop is the good direction for power: no flag.
    assert health.control_chart(base + [0.20], "up", 0.001)["status"] == "normal"
    # For the heating rate, lower is worse.
    assert health.control_chart([4.0, 4.1, 3.9, 4.0, 4.1, 3.0], "down", 0.01)["status"] == "attention"


def test_eight_jobs_on_the_worse_side_is_a_drift():
    base = [0.30, 0.31, 0.29, 0.30, 0.31] * 2
    chart = health.control_chart(base + [0.312] * 8, "up", 0.001)
    assert chart["flags"][-1] == ["eight_on_worse_side"]
    assert "deriva" in chart["findings"][-1]
    assert health.control_chart(base + [0.312] * 7, "up", 0.001)["status"] == "normal"


def test_identical_jobs_do_not_turn_noise_into_anomalies():
    assert health.control_chart([0.3] * 5 + [0.3005], "up", 0.001)["status"] == "normal"
    assert health.control_chart([0.3] * 5 + [0.305], "up", 0.001)["status"] == "attention"


def test_printer_health_endpoint_flags_a_heater_needing_more_power(with_db):
    health._cache.clear()

    async def scenario(session_factory):
        async with session_factory() as db:
            user = User(username=f"t-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local",
                        hashed_password="x", role=UserRole.admin)
            printer = Printer(name="Simulada", octoprint_url="http://mock", octoprint_api_key_encrypted="",
                              integration_type=IntegrationType.moonraker)
            db.add_all([user, printer])
            await db.flush()
            powers = [0.30, 0.31, 0.29, 0.30, 0.31, 0.30, 0.45]
            for index, power in enumerate(powers):
                started = START + timedelta(days=index)
                job = PrintJob(printer_id=printer.id, file_name=f"pieza_{index}.gcode", status=JobStatus.completed,
                               started_at=started, ended_at=started + timedelta(seconds=200))
                db.add(job)
                await db.flush()
                for sample in _job_samples(started, hold_power=power):
                    db.add(TelemetrySample(print_job_id=job.id, **sample))
            db.add(PrintJob(printer_id=printer.id, file_name="en_curso.gcode", status=JobStatus.running,
                            started_at=START + timedelta(days=30)))
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await client.get(f"/api/v1/printers/{printer.id}/health"), await client.get("/api/v1/printers/999/health")
        finally:
            app.dependency_overrides.clear()

    response, missing = with_db(scenario)
    assert missing.status_code == 404
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["jobs_considered"], body["jobs_with_telemetry"]) == (7, 7)  # the running job is left out
    extruder, bed = body["heaters"]
    assert extruder["target_bucket"] == 240.0
    metrics = {metric["key"]: metric for metric in extruder["metrics"]}
    assert metrics["hold_power"]["status"] == "attention"
    assert metrics["hold_power"]["baseline"]["n"] == 5  # the last jobs stay out of the baseline
    assert metrics["hold_power"]["points"][-1]["flags"] == ["beyond_3sigma"]
    assert metrics["oscillation"]["status"] == "normal"
    assert metrics["heating_rate"]["status"] == "normal"
    assert all(metric["status"] == "insufficient" and metric["points"] == [] for metric in bed["metrics"])
