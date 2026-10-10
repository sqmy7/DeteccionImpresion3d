"""The spaghetti auto-pause in its three modes (AUTO_PAUSE_MODE), against the simulated printer, which
really changes state when it receives a pause: "on" pauses it, "warn" and "off" never send anything."""

import asyncio
import time
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, settings
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
)
from app.integrations.moonraker import command_log
from app.services import auto_pause
from app.services.printer_events import verify_chain

CONFIDENCES = {7: 0.81, 8: 0.64, 9: 0.92}  # three layers in a row with spaghetti


async def _state(mock: httpx.AsyncClient) -> str:
    response = await mock.get("/printer/objects/query", params={"print_stats": "state"})
    return response.json()["result"]["status"]["print_stats"]["state"]


def _run_streak(mock_server, with_db, monkeypatch, mode: str) -> dict:
    """Three layers of spaghetti on a printing job; the streak check runs once, as the detection of
    the third layer arrives. Returns what happened to the printer and in the event log."""
    monkeypatch.setattr(settings, "auto_pause_mode", mode)
    monkeypatch.setattr(auto_pause, "_GRACE_PERIOD_SECONDS", 0.05)
    monkeypatch.setattr(auto_pause, "_CONFIRM_POLL_SECONDS", 0.05)

    async def scenario(session_factory):
        command_log._commands.clear()
        manager = auto_pause.AutoPauseManager()
        async with session_factory() as db:
            printer = Printer(name="Simulada", octoprint_url=mock_server, octoprint_api_key_encrypted="",
                              integration_type=IntegrationType.moonraker)
            db.add(printer)
            await db.flush()
            camera = Camera(printer_id=printer.id, name="C922", source_type=CameraSourceType.usb, source_uri="0",
                            role=CameraRole.primary)
            model = ModelVersion(name=f"test-{uuid.uuid4().hex[:6]}", file_path="test.onnx", classes=["spaghetti"])
            job = PrintJob(printer_id=printer.id, file_name="mock_box.gcode", status=JobStatus.running)
            db.add_all([camera, model, job])
            await db.flush()
            for number, confidence in CONFIDENCES.items():
                layer = Layer(job_id=job.id, layer_number=number, z_height=Decimal("0.2") * number, telemetry={})
                db.add(layer)
                await db.flush()
                capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"{number}.jpg")
                db.add(capture)
                await db.flush()
                db.add(Detection(capture_id=capture.id, model_version_id=model.id, has_defect=True,
                                 max_confidence=Decimal(str(confidence)), defect_classes=["spaghetti"], raw_output={}))
            await db.commit()
            ids = (printer.id, camera.id, job.id)

        async with httpx.AsyncClient(base_url=mock_server) as mock:
            (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
            assert await _state(mock) == "printing"
            await manager.check_spaghetti_streak(session_factory, job_id=ids[2], camera_id=ids[1], printer_id=ids[0])
            pending_right_after = bool(manager._pending)
            await asyncio.sleep(0.6)  # well past the (shortened) grace period
            if mode == "on":  # slow machine: wait for the printer's confirmation instead of a fixed time
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    async with session_factory() as db:
                        confirmed = await db.scalar(
                            select(PrinterEvent.id).where(PrinterEvent.printer_id == ids[0],
                                                          PrinterEvent.event_type == "auto_pause.confirmed")
                        )
                    if confirmed is not None:
                        break
                    await asyncio.sleep(0.1)
            state = await _state(mock)

        async with session_factory() as db:
            events = (await db.execute(
                select(PrinterEvent).where(PrinterEvent.printer_id == ids[0]).order_by(PrinterEvent.id)
            )).scalars().all()
            chain = await verify_chain(db, ids[0])
        pauses = [c for c in command_log._commands if c.base_url == mock_server and c.action == "pause"]
        return {"state": state, "pauses": len(pauses), "pending": pending_right_after, "events": events,
                "chain": chain, "job_id": ids[2]}

    return with_db(scenario)


def test_on_pauses_the_printer_as_before(mock_server, with_db, monkeypatch):
    result = _run_streak(mock_server, with_db, monkeypatch, "on")

    assert result["pending"] is True  # the countdown started
    assert result["state"] == "paused" and result["pauses"] == 1
    # The pause order itself is logged by the Moonraker listener; the auto-pause now logs its countdown and the
    # printer's own confirmation (see test_incidents.py for the incident that goes with them).
    assert [e.event_type for e in result["events"]] == ["auto_pause.pending", "auto_pause.confirmed"]


def test_warn_logs_what_it_would_have_done_and_sends_nothing(mock_server, with_db, monkeypatch):
    result = _run_streak(mock_server, with_db, monkeypatch, "warn")

    assert result["state"] == "printing" and result["pauses"] == 0
    assert result["pending"] is False  # no countdown either
    (event,) = result["events"]
    assert event.event_type == "auto_pause.would_pause" and event.origin == "monitor"
    assert event.print_job_id == result["job_id"]
    assert event.detail["sent"] is False and event.detail["mode"] == "warn"
    assert event.detail["layer"] == 9 and event.detail["confidence"] == 0.92  # the layer that completed the streak
    assert [item["layer"] for item in event.detail["streak"]] == [9, 8, 7]
    assert event.ts is not None
    assert result["chain"]["ok"] is True and result["chain"]["events_checked"] == 1


def test_off_does_nothing_at_all(mock_server, with_db, monkeypatch):
    result = _run_streak(mock_server, with_db, monkeypatch, "off")

    assert result["state"] == "printing" and result["pauses"] == 0
    assert result["pending"] is False
    assert result["events"] == []


def test_the_mode_defaults_to_on_and_a_typo_stops_the_backend(monkeypatch):
    env = {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db", "REDIS_URL": "redis://localhost",
           "JWT_SECRET_KEY": "k", "FIELD_ENCRYPTION_KEY": "a" * 44}
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    monkeypatch.delenv("AUTO_PAUSE_MODE", raising=False)
    assert Settings(_env_file=None).auto_pause_mode == "on"
    monkeypatch.setenv("AUTO_PAUSE_MODE", " Warn ")
    assert Settings(_env_file=None).auto_pause_mode == "warn"
    monkeypatch.setenv("AUTO_PAUSE_MODE", "maybe")
    with pytest.raises(ValueError, match="AUTO_PAUSE_MODE"):
        Settings(_env_file=None)
