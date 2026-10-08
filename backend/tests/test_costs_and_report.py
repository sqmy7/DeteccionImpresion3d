"""Cost estimate (filament and heater energy at configured prices) and the job's PDF report."""

import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.api.deps import get_current_user, require_admin
from app.db.models import (
    Camera,
    CameraRole,
    CameraSourceType,
    Detection,
    IntegrationType,
    JobStatus,
    Layer,
    LayerCapture,
    ModelVersion,
    Printer,
    PrinterEvent,
    PrintJob,
    TelemetrySample,
    User,
    UserRole,
)
from app.db.session import get_db
from app.main import app
from app.services import costs, printer_events, report

START = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
SETTINGS = {**costs.DEFAULTS, "is_default": True, "updated_at": None}


def test_filament_grams_prefer_the_slicer_weight():
    file = {"filament_total": 10000.0, "filament_weight_total": 30.0, "filament_type": "PLA"}
    grams = costs.filament_grams(5000.0, file, SETTINGS)
    assert grams["method"] == "slicer" and grams["grams"] == pytest.approx(15.0)


def test_filament_grams_from_the_material_density():
    grams = costs.filament_grams(1000.0, {"filament_type": "PETG-CF"}, SETTINGS)
    area = math.pi * (1.75 / 2) ** 2
    assert grams["method"] == "density" and grams["density"] == 1.27 and grams["material"] == "PETG"
    assert grams["grams"] == pytest.approx(1000 * area * 1.27 / 1000)  # ~3.05 g per metre
    unknown = costs.filament_grams(1000.0, {}, SETTINGS)
    assert unknown["density"] == SETTINGS["default_density_g_cm3"]


def test_heater_energy_integrates_pwm_and_skips_gaps():
    samples = [{"ts": START + timedelta(seconds=second), "extruder_power": 0.5, "bed_power": 1.0} for second in range(3600)]
    # A one-minute gap (backend down) is not guessed.
    samples += [{"ts": START + timedelta(seconds=3660 + second), "extruder_power": 0.5, "bed_power": 1.0} for second in range(10)]
    energy = costs.heater_energy_wh(samples, SETTINGS)
    seconds = 3599 + 10  # one 60 s step skipped; the last sample counts 1 s
    assert energy["covered_seconds"] == seconds
    assert energy["extruder_wh"] == pytest.approx(0.5 * 50 * seconds / 3600)
    assert energy["bed_wh"] == pytest.approx(1.0 * 300 * seconds / 3600)


async def _seed_job(session_factory, *, with_telemetry: bool) -> tuple[User, PrintJob]:
    async with session_factory() as db:
        user = User(username=f"t-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local",
                    hashed_password="x", role=UserRole.admin)
        printer = Printer(name="Simulada", octoprint_url="http://mock", octoprint_api_key_encrypted="",
                          integration_type=IntegrationType.moonraker)
        db.add_all([user, printer])
        await db.flush()
        camera = Camera(printer_id=printer.id, name="C922", source_type=CameraSourceType.usb, source_uri="0", role=CameraRole.primary)
        model = ModelVersion(name=f"test-{uuid.uuid4().hex[:6]}", file_path="t.onnx", classes=["under_extrusion"])
        geometry = {
            "axis_minimum": [0, 0, 0, 0], "axis_maximum": [260.0, 260.0, 300.0, 0.0], "bed_mesh": None,
            "objects": [{"name": "BOX_1", "center": [95.0, 130.0], "polygon": [[70, 105], [120, 105], [120, 155], [70, 155]]}],
            "file": {"estimated_time": 100, "filament_total": 2000.0, "filament_type": "PLA"},
        }
        job = PrintJob(printer_id=printer.id, file_name="pieza ñandú.gcode", status=JobStatus.completed, started_at=START,
                       ended_at=START + timedelta(seconds=120), estimated_layers=4, geometry=geometry)
        db.add_all([camera, model, job])
        await db.flush()
        if with_telemetry:
            for second in range(120):
                db.add(TelemetrySample(
                    print_job_id=job.id, ts=START + timedelta(seconds=second), layer_number=1 + second // 30,
                    extruder_temp=239.8 if second % 2 else 240.2, extruder_target=240.0, extruder_power=0.4,
                    bed_temp=70.0, bed_target=70.0, bed_power=0.5, speed_factor=1.0, extrude_factor=0.9 if second >= 60 else 1.0,
                    fan_speed=1.0, filament_used=float(second * 15), x=95.0, y=130.0,
                ))
        for number in range(1, 5):
            layer = Layer(job_id=job.id, layer_number=number, z_height=Decimal(str(number * 0.2)),
                          detected_at=START + timedelta(seconds=(number - 1) * 30))
            db.add(layer)
            await db.flush()
            capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"{number}.jpg")
            db.add(capture)
            await db.flush()
            boxes = [{"class": "under_extrusion", "confidence": 0.6, "box": [0.1, 0.1, 0.2, 0.2]}] if number == 4 else []
            db.add(Detection(capture_id=capture.id, model_version_id=model.id, has_defect=bool(boxes),
                             max_confidence=Decimal("0.6") if boxes else None,
                             defect_classes=[box["class"] for box in boxes], raw_output={"detections": boxes}))
        await db.commit()

    for kind, origin, field, before, after, at in (
        ("state_changed", "external", "print_stats.state", "standby", "printing", 0),
        ("flow_factor_changed", "console", "gcode_move.extrude_factor", 1.0, 0.9, 60),
        ("state_changed", "printer", "print_stats.state", "printing", "complete", 120),
    ):
        await printer_events.record_event(session_factory, job.printer_id, kind, printer_events.EventOrigin(origin), job_id=job.id,
                                          field=field, before=before, after=after, ts=START + timedelta(seconds=at))
    return user, job


def _client_for(session_factory, user):
    async def test_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def test_job_cost_with_default_then_saved_settings(with_db):
    async def scenario(session_factory):
        user, job = await _seed_job(session_factory, with_telemetry=True)
        try:
            async with _client_for(session_factory, user) as client:
                before = await client.get(f"/api/v1/print-jobs/{job.id}/cost")
                settings = await client.get("/api/v1/settings/costs")
                bad = await client.put("/api/v1/settings/costs", json={**costs.DEFAULTS, "bed_heater_w": -5})
                saved = await client.put("/api/v1/settings/costs", json={**costs.DEFAULTS, "filament_price_per_kg": 100000})
                after = await client.get(f"/api/v1/print-jobs/{job.id}/cost")
        finally:
            app.dependency_overrides.clear()
        return before, settings, bad, saved, after

    before, settings, bad, saved, after = with_db(scenario)
    assert settings.json()["is_default"] is True
    body = before.json()
    assert body["settings_are_default"] is True
    filament = body["filament"]
    assert filament["used_mm"] == 1785.0 and filament["method"] == "density" and filament["material"] == "PLA"
    assert filament["used_g"] == pytest.approx(1785 * math.pi * 0.875**2 * 1.24 / 1000, abs=0.01)
    assert filament["estimated_mm"] == 2000.0
    energy = body["energy"]
    assert energy["covered_seconds"] == 120
    assert energy["extruder_wh"] == pytest.approx(0.4 * 50 * 120 / 3600, abs=0.01)
    assert energy["bed_wh"] == pytest.approx(0.5 * 300 * 120 / 3600, abs=0.01)
    assert body["total_cost"] == pytest.approx(filament["cost"] + energy["cost"], abs=0.02)

    assert bad.status_code == 422
    assert saved.status_code == 200 and saved.json()["is_default"] is False
    assert after.json()["filament"]["cost"] == pytest.approx(filament["cost"] * 100000 / 80000, abs=0.02)


def test_pdf_report_with_and_without_telemetry(with_db):
    async def scenario(session_factory):
        user, job = await _seed_job(session_factory, with_telemetry=True)
        try:
            async with _client_for(session_factory, user) as client:
                full = await client.get(f"/api/v1/print-jobs/{job.id}/report.pdf")
                missing = await client.get("/api/v1/print-jobs/9999/report.pdf")
        finally:
            app.dependency_overrides.clear()
        async with session_factory() as db:
            bare = PrintJob(printer_id=job.printer_id, file_name="sin_telemetria.gcode", status=JobStatus.running, started_at=START)
            db.add(bare)
            await db.commit()
            bare_pdf = await report.build_report(db, bare)
        return full, missing, bare_pdf

    full, missing, bare_pdf = with_db(scenario)
    assert missing.status_code == 404
    assert full.status_code == 200, full.text
    assert full.headers["content-type"] == "application/pdf"
    assert full.headers["content-disposition"].startswith('attachment; filename="reporte_trabajo_')
    assert full.content.startswith(b"%PDF-") and full.content.rstrip().endswith(b"%%EOF")
    pages = re.search(rb"/Count (\d+)", full.content)
    assert pages and int(pages.group(1)) >= 2  # summary and charts, then map, defects, log and notes
    assert bare_pdf.startswith(b"%PDF-")


def test_report_text_helpers():
    assert report._num(12345.678, 1) == "12.345,7"
    assert report._money(80000, "COP") == "80.000 COP"
    assert report._duration(3725) == "1 h 02 min"
    assert report._t("1 → 2 ≥ σ") == "1 -> 2 >= sigma"
    event = PrinterEvent(event_type="flow_factor_changed", field="gcode_move.extrude_factor", value_before=1.0, value_after=0.9,
                         origin="console", detail=None)
    assert report.describe_event(event) == "Flujo: 100 % -> 90 %"


def test_density_method_matches_the_slicer_on_the_real_print():
    """Measured on job 43 of the real Hi (docs/laboratorio/analisis_trabajo_43.md): the printer reported 68,220 mm
    of filament used; the slicer's weight for the whole file is 201.83 g. Density x diameter gives +3.1 %, so
    the density method is what the cost uses (the +3 % is purge and priming the slicer doesn't count, plus the
    material's nominal density)."""
    file = {"filament_type": "PETG", "filament_weight_total": 201.83}
    grams = costs.filament_grams(68220.0, file, SETTINGS)
    assert grams["method"] == "density" and grams["material"] == "PETG"
    assert grams["grams"] == pytest.approx(208.4, abs=0.1)
    assert abs(grams["grams"] / 201.83 - 1) < 0.04