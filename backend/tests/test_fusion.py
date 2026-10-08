"""Combined score: model confidence raised by telemetry signals of the layer just printed."""

import struct
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.api.deps import get_current_user
from app.db.models import (
    Camera,
    CameraRole,
    CameraSourceType,
    Detection,
    IntegrationType,
    Layer,
    LayerCapture,
    ModelVersion,
    Printer,
    PrintJob,
    TelemetrySample,
    User,
    UserRole,
)
from app.db.session import get_db
from app.main import app
from app.services import fusion


def _sample(layer: int, **values) -> dict:
    base = {
        "layer_number": layer,
        "extruder_temp": 240.0,
        "extruder_target": 240.0,
        "extruder_power": 0.4,
        "bed_temp": 70.0,
        "bed_target": 70.0,
        "extrude_factor": 1.0,
        "speed_factor": 1.0,
        "extra": None,
    }
    return {**base, **values}


def _float32(value: float) -> float:
    """What a REAL column gives back."""
    return struct.unpack("f", struct.pack("f", value))[0]


def _signals(outcome: dict) -> dict:
    return {signal["key"]: signal for signal in outcome["signals"]}


def test_normal_telemetry_leaves_the_model_confidence():
    stats = fusion.window_stats([_sample(4) for _ in range(12)])
    outcome = fusion.evaluate("under_extrusion", 0.6, stats, {"nozzle_target": 240.0, "bed_target": 70.0})
    assert outcome["score"] == 0.6
    signals = _signals(outcome)
    assert set(signals) == {"no_filament", "heater_saturated", "nozzle_cold", "flow_low", "speed_high"}
    assert not any(signal["met"] for signal in signals.values())
    assert signals["nozzle_cold"]["value"] == 0.0
    assert signals["no_filament"]["value"] is None  # this printer has no filament sensor


def test_cold_nozzle_raises_under_extrusion_by_its_weight():
    stats = fusion.window_stats([_sample(4, extruder_temp=232.0) for _ in range(12)])
    outcome = fusion.evaluate("under_extrusion", 0.6, stats, {})
    assert _signals(outcome)["nozzle_cold"] == {
        "key": "nozzle_cold", "label": "Boquilla por debajo del objetivo", "unit": "°C", "operator": ">",
        "threshold": 5.0, "weight": fusion.MEDIUM, "value": 8.0, "met": True,
    }
    assert outcome["score"] == pytest.approx(1 - 0.4 * (1 - fusion.MEDIUM), abs=1e-3)


def test_a_deviation_inside_klippers_band_is_not_a_signal():
    stats = fusion.window_stats([_sample(4, extruder_temp=236.0) for _ in range(12)])
    assert not _signals(fusion.evaluate("under_extrusion", 0.6, stats, {}))["nozzle_cold"]["met"]


def test_signals_combine_as_noisy_or():
    samples = [
        _sample(4, extruder_temp=230.0, extruder_power=1.0, extra={"filament_switch_sensor fs.filament_detected": False})
        for _ in range(12)
    ]
    outcome = fusion.evaluate("under_extrusion", 0.5, fusion.window_stats(samples), {})
    met = [key for key, signal in _signals(outcome).items() if signal["met"]]
    assert met == ["no_filament", "heater_saturated", "nozzle_cold"]
    expected = 1 - 0.5 * (1 - fusion.STRONG) * (1 - fusion.MEDIUM) * (1 - fusion.MEDIUM)
    assert outcome["score"] == pytest.approx(expected, abs=1e-3)
    assert outcome["score"] < 1


def test_flow_change_of_one_calibration_step_counts_even_as_stored_in_real_columns():
    raised = fusion.window_stats([_sample(4, extrude_factor=_float32(1.05)) for _ in range(12)])
    lowered = fusion.window_stats([_sample(4, extrude_factor=_float32(0.95)) for _ in range(12)])
    assert _signals(fusion.evaluate("blob_over_extrusion", 0.3, raised, {}))["flow_high"]["met"]
    assert _signals(fusion.evaluate("under_extrusion", 0.3, lowered, {}))["flow_low"]["met"]


def test_bed_lowered_against_the_first_layer_raises_warping():
    initial = fusion.initial_targets([_sample(0, bed_target=0.0), _sample(1, bed_target=70.0)])
    assert initial == {"nozzle_target": 240.0, "bed_target": 70.0}
    stats = fusion.window_stats([_sample(9, bed_target=60.0, bed_temp=60.5) for _ in range(12)])
    signals = _signals(fusion.evaluate("warping", 0.5, stats, initial))
    assert signals["bed_lowered"]["value"] == 10.0 and signals["bed_lowered"]["met"]
    assert not signals["bed_cold"]["met"]  # it is holding its new target


def test_spaghetti_has_no_telemetry_signals():
    stats = fusion.window_stats([_sample(4, extruder_temp=200.0) for _ in range(12)])
    assert fusion.evaluate("spaghetti", 0.81, stats, {}) == {"score": 0.81, "signals": []}


def test_window_is_the_layer_before_the_photo_plus_earlier_ones_when_short():
    by_layer = {3: [_sample(3)] * 6, 4: [_sample(4)] * 3, 5: [_sample(5)] * 20}
    window, layers = fusion.layer_window(by_layer, 5)  # the photo at layer 5 shows layer 4 on top
    assert layers == [3, 4] and len(window) == 9  # still short, but no more layers before 3 here
    window, layers = fusion.layer_window(by_layer, 6)
    assert layers == [5] and len(window) == 20


def test_job_fusion_endpoint_scores_each_box(with_db):
    start = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    async def scenario(session_factory):
        async with session_factory() as db:
            user = User(username=f"t-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local",
                        hashed_password="x", role=UserRole.admin)
            printer = Printer(name="Simulada", octoprint_url="http://mock", octoprint_api_key_encrypted="",
                              integration_type=IntegrationType.moonraker)
            db.add_all([user, printer])
            await db.flush()
            camera = Camera(printer_id=printer.id, name="C922", source_type=CameraSourceType.usb, source_uri="0",
                            role=CameraRole.primary)
            model = ModelVersion(name=f"test-{uuid.uuid4().hex[:6]}", file_path="t.onnx", classes=["under_extrusion"])
            job = PrintJob(printer_id=printer.id, file_name="pieza.gcode")
            db.add_all([camera, model, job])
            await db.flush()
            for second in range(60):
                layer_number = 1 + second // 15  # layers 1-4, 15 s each
                cold = layer_number == 3
                db.add(TelemetrySample(
                    print_job_id=job.id, ts=start + timedelta(seconds=second), layer_number=layer_number,
                    extruder_temp=229.0 if cold else 240.2, extruder_target=240.0, extruder_power=0.5,
                    bed_temp=70.0, bed_target=70.0, extrude_factor=1.0, speed_factor=1.0,
                ))
            for number, confidence in ((4, 0.6), (5, 0.6)):
                layer = Layer(job_id=job.id, layer_number=number, z_height=Decimal("1.0"))
                db.add(layer)
                await db.flush()
                capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"{number}.jpg")
                db.add(capture)
                await db.flush()
                db.add(Detection(
                    capture_id=capture.id, model_version_id=model.id, has_defect=True,
                    max_confidence=Decimal(str(confidence)), defect_classes=["under_extrusion", "spaghetti"],
                    raw_output={"detections": [
                        {"class": "under_extrusion", "confidence": confidence, "box": [0.1, 0.1, 0.2, 0.2]},
                        {"class": "spaghetti", "confidence": 0.3, "box": [0.3, 0.3, 0.4, 0.4]},
                    ]},
                ))
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await client.get(f"/api/v1/print-jobs/{job.id}/fusion")
        finally:
            app.dependency_overrides.clear()

    response = with_db(scenario)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"]["calibrated"] is False
    items = {(item["layer_number"], item["class_name"]): item for item in body["items"]}
    assert len(items) == 4

    # The photo at layer 4 shows layer 3, printed with the nozzle 11 °C cold.
    cold = items[(4, "under_extrusion")]
    assert cold["window"] == {"source": "telemetry", "samples": 15, "layers": [3]}
    assert cold["score"] == pytest.approx(1 - 0.4 * (1 - fusion.MEDIUM), abs=1e-3)
    assert items[(5, "under_extrusion")]["score"] == 0.6  # layer 4 was printed normally
    assert items[(4, "spaghetti")]["score"] == 0.3 and items[(4, "spaghetti")]["box_index"] == 1
