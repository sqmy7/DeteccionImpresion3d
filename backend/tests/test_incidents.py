"""Incidents: the record of what the model saw, what PrintWatch did and what the user decided.

Against the simulated printer (which really changes state when it receives a pause) and the test database.
Nothing here reaches a real printer."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import get_current_user, require_admin
from app.api.v1.incidents import boxes_on_frame
from app.core.config import settings
from app.db.models import (
    Camera,
    CameraRole,
    CameraSourceType,
    Detection,
    Incident,
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
from app.integrations.moonraker import command_log
from app.main import app
from app.services import auto_pause, incidents
from app.services.printer_events import verify_chain

CONFIDENCES = {7: 0.81, 8: 0.64, 9: 0.92}  # three layers in a row with spaghetti
FRAME = {"width": 1280, "height": 720, "roi": {"x": 0, "y": 0, "w": 1280, "h": 720}}
BASE = datetime.now(timezone.utc) - timedelta(seconds=90)


def _raw(confidence: float, klass: str = "spaghetti") -> dict:
    return {"detections": [{"class": klass, "confidence": confidence, "box": [0.2, 0.3, 0.4, 0.6]}], "frame": FRAME}


async def _state(mock: httpx.AsyncClient) -> str:
    response = await mock.get("/printer/objects/query", params={"print_stats": "state"})
    return response.json()["result"]["status"]["print_stats"]["state"]


async def seed(session_factory, mock_server: str, *, layers: dict[int, float] = CONFIDENCES) -> dict:
    """A running job on the simulated printer, with a photo and a spaghetti detection for each layer and a
    little telemetry (the printer's own print clock included)."""
    async with session_factory() as db:
        printer = Printer(name="Simulada", octoprint_url=mock_server, octoprint_api_key_encrypted="",
                          integration_type=IntegrationType.moonraker)
        db.add(printer)
        await db.flush()
        camera = Camera(printer_id=printer.id, name="C922", source_type=CameraSourceType.usb, source_uri="0",
                        role=CameraRole.primary)
        model = ModelVersion(name=f"test-{uuid.uuid4().hex[:6]}", file_path="test.onnx", classes=["spaghetti"])
        job = PrintJob(
            printer_id=printer.id, file_name="cubo_PETG_2m28s.gcode", status=JobStatus.running,
            geometry={"file": {"estimated_time": 148, "estimated_time_source": "filename"}},
        )
        db.add_all([camera, model, job])
        await db.flush()
        for position, (number, confidence) in enumerate(layers.items()):
            layer = Layer(job_id=job.id, layer_number=number, z_height=Decimal("0.2") * number,
                          telemetry={"x": 130.0 + number, "y": 130.0, "extruder_temp": 250.0, "speed_factor": 1.0})
            db.add(layer)
            await db.flush()
            capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"{printer.id}/{job.id}/layer_{number}_primary.jpg",
                                   captured_at=BASE + timedelta(seconds=10 * position))
            db.add(capture)
            await db.flush()
            db.add(Detection(capture_id=capture.id, model_version_id=model.id, has_defect=True,
                             max_confidence=Decimal(str(confidence)), defect_classes=["spaghetti"], raw_output=_raw(confidence)))
        for second in range(5):
            db.add(TelemetrySample(
                print_job_id=job.id, ts=BASE + timedelta(seconds=25 + second), layer_number=9, x=139.0, y=130.0, z=1.8,
                extruder_temp=249.5, extruder_target=250.0, bed_temp=80.0, bed_target=80.0, speed_factor=1.0,
                extrude_factor=1.0, fan_speed=0.4, progress=0.5, extra={"print_stats.print_duration": 60.0 + second},
            ))
        await db.commit()
        return {"printer": printer.id, "camera": camera.id, "job": job.id}


async def incidents_of(session_factory, job_id: int) -> list[Incident]:
    async with session_factory() as db:
        return list((await db.execute(select(Incident).where(Incident.print_job_id == job_id).order_by(Incident.id))).scalars())


async def events_of(session_factory, printer_id: int) -> list[PrinterEvent]:
    async with session_factory() as db:
        return list((await db.execute(select(PrinterEvent).where(PrinterEvent.printer_id == printer_id).order_by(PrinterEvent.id))).scalars())


async def settled(manager: auto_pause.AutoPauseManager, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while manager._pending:
        assert asyncio.get_running_loop().time() < deadline, "the auto-pause did not finish"
        await asyncio.sleep(0.05)


def prepare(monkeypatch, mode: str, *, grace: float = 0.05, confirm: float = 20.0, poll: float = 0.05) -> None:
    monkeypatch.setattr(settings, "auto_pause_mode", mode)
    monkeypatch.setattr(auto_pause, "_GRACE_PERIOD_SECONDS", grace)
    monkeypatch.setattr(auto_pause, "_CONFIRM_TIMEOUT_SECONDS", confirm)
    monkeypatch.setattr(auto_pause, "_CONFIRM_POLL_SECONDS", poll)
    command_log._commands.clear()


async def start_print(mock_server: str) -> None:
    async with httpx.AsyncClient(base_url=mock_server) as mock:
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        assert await _state(mock) == "printing"


# ------------------------------------------------------------------ warn and on

def test_warn_mode_opens_an_incident_with_the_evidence_and_sends_nothing(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "warn")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        await start_print(mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        async with httpx.AsyncClient(base_url=mock_server) as mock:
            state = await _state(mock)
        return ids, state, await incidents_of(session_factory, ids["job"]), await events_of(session_factory, ids["printer"])

    ids, state, found, events = with_db(scenario)

    assert state == "printing"
    (incident,) = found
    assert (incident.reason, incident.mode, incident.defect_class, incident.status) == ("would_pause", "warn", "spaghetti", "open")
    assert [(item["layer"], item["confidence"]) for item in incident.streak] == [(7, 0.81), (8, 0.64), (9, 0.92)]
    assert all(item["detection_id"] and item["capture_id"] for item in incident.streak)
    assert incident.detection_id == incident.streak[-1]["detection_id"]
    assert incident.first_defect_at == BASE  # the first photo of the streak
    assert incident.announced_at is not None and incident.pause_sent_at is None and incident.paused_at is None
    assert incident.label == "unlabeled" and incident.outcome is None and incident.camera_id == ids["camera"]
    # the printer as it was: the latest sample, the layer's telemetry row and the time left by the slicer's estimate
    snapshot = incident.telemetry_snapshot
    assert snapshot["sample"]["extruder_temp"] == 249.5 and snapshot["sample"]["bed_target"] == 80.0
    assert snapshot["layer"]["layer_number"] == 9 and snapshot["layer"]["telemetry"]["speed_factor"] == 1.0
    assert snapshot["printed_s"] == 64.0 and snapshot["remaining_s"] == 84.0
    # the event log says the same and points at the incident
    (event,) = [e for e in events if e.event_type == "auto_pause.would_pause"]
    assert event.detail["incident_id"] == incident.id and event.detail["sent"] is False
    assert not [c for c in command_log._commands if c.action == "pause"]


def test_on_mode_logs_the_countdown_sends_the_pause_and_confirms_klipper_paused(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "on")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        await start_print(mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        await settled(manager)
        async with httpx.AsyncClient(base_url=mock_server) as mock:
            state = await _state(mock)
        async with session_factory() as db:
            chain = await verify_chain(db, ids["printer"])
        return ids, state, await incidents_of(session_factory, ids["job"]), await events_of(session_factory, ids["printer"]), chain

    ids, state, found, events, chain = with_db(scenario)

    assert state == "paused"
    (incident,) = found
    assert (incident.reason, incident.mode, incident.status, incident.outcome) == ("auto_pause", "on", "paused", None)
    assert incident.announced_at <= incident.pause_sent_at <= incident.paused_at
    assert incident.detail["pause_origin"] == "printwatch"
    kinds = [e.event_type for e in events]
    assert kinds.index("auto_pause.pending") < kinds.index("auto_pause.confirmed")
    pending = next(e for e in events if e.event_type == "auto_pause.pending")
    assert pending.detail["incident_id"] == incident.id and pending.detail["grace_seconds"] == auto_pause._GRACE_PERIOD_SECONDS
    assert next(e for e in events if e.event_type == "auto_pause.confirmed").detail["incident_id"] == incident.id
    assert "auto_pause.not_confirmed" not in kinds
    assert chain["ok"] is True


def test_aborting_the_countdown_closes_the_incident_as_ignored_and_logs_who(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "on", grace=30.0)

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        await start_print(mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        first = await manager.abort(ids["job"], requested_by="samuel (web)")
        second = await manager.abort(ids["job"], requested_by="samuel (web)")  # nothing left to abort
        await asyncio.sleep(0.1)
        async with httpx.AsyncClient(base_url=mock_server) as mock:
            state = await _state(mock)
        return ids, first, second, state, await incidents_of(session_factory, ids["job"]), await events_of(session_factory, ids["printer"])

    ids, first, second, state, found, events = with_db(scenario)

    assert (first, second) == (True, False)
    assert state == "printing"
    (incident,) = found
    assert (incident.status, incident.outcome, incident.decided_by) == ("closed", "ignored", "samuel (web)")
    assert incident.decided_at is not None and incident.pause_sent_at is None
    aborted = next(e for e in events if e.event_type == "auto_pause.aborted")
    assert aborted.detail == {"incident_id": incident.id, "requested_by": "samuel (web)"}
    assert [e.event_type for e in events][:2] == ["auto_pause.pending", "auto_pause.aborted"]


def test_an_abort_after_the_pause_is_sent_is_refused(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "on", confirm=3.0)

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        await start_print(mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        await asyncio.sleep(0.4)  # the grace period (0.05 s) is over; confirmation may still be running
        late = await manager.abort(ids["job"], requested_by="samuel (web)")
        await settled(manager)
        return late, await incidents_of(session_factory, ids["job"])

    late, found = with_db(scenario)
    assert late is False
    assert found[0].status == "paused" and found[0].outcome is None


# ------------------------------------------------------------------ pause not confirmed

def test_a_pause_that_klipper_never_confirms_is_marked_not_confirmed(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "on", confirm=0.5, poll=0.1)
    sent = []

    async def pause_that_does_nothing(base_url: str, action: str, requested_by: str | None = None) -> None:
        sent.append(action)  # accepted by the printer's API, but the printer keeps printing

    monkeypatch.setattr(auto_pause, "send_print_action", pause_that_does_nothing)

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        await start_print(mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        await settled(manager)
        found = await incidents_of(session_factory, ids["job"])
        # Klipper pauses later (someone pauses it): the listener's report completes the picture.
        await incidents.on_state_change(
            session_factory, printer_id=ids["printer"], job_id=ids["job"], previous_state="printing", new_state="paused",
            origin="external", order=None,
        )
        return ids, found, await incidents_of(session_factory, ids["job"]), await events_of(session_factory, ids["printer"])

    ids, before, after, events = with_db(scenario)

    assert sent == ["pause"]
    assert before[0].status == "unconfirmed" and before[0].pause_sent_at is not None and before[0].paused_at is None
    assert before[0].detail["unconfirmed"]["reason"] == "timeout" and before[0].detail["unconfirmed"]["last_state"] == "printing"
    not_confirmed = next(e for e in events if e.event_type == "auto_pause.not_confirmed")
    assert not_confirmed.detail["reason"] == "timeout" and not_confirmed.detail["incident_id"] == before[0].id
    assert "auto_pause.confirmed" not in [e.event_type for e in events]
    assert after[0].status == "paused" and after[0].paused_at is not None  # late confirmation from the printer's own report


def test_a_pause_that_cannot_be_sent_is_recorded_as_not_confirmed(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "on")

    async def unreachable(base_url: str, action: str, requested_by: str | None = None) -> None:
        raise httpx.ConnectError("the printer does not answer")

    monkeypatch.setattr(auto_pause, "send_print_action", unreachable)

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        await start_print(mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        await settled(manager)
        return await incidents_of(session_factory, ids["job"]), await events_of(session_factory, ids["printer"])

    found, events = with_db(scenario)
    assert found[0].status == "unconfirmed"
    assert found[0].detail["unconfirmed"]["reason"] == "send_failed" and "ConnectError" in found[0].detail["unconfirmed"]["error"]
    assert next(e for e in events if e.event_type == "auto_pause.not_confirmed").detail["reason"] == "send_failed"


def test_off_mode_leaves_no_incident(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "off")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        return await incidents_of(session_factory, ids["job"])

    assert with_db(scenario) == []


# ------------------------------------------------------------------ idempotence, detections, state changes

def test_one_unclosed_incident_per_job_and_class_and_a_closed_one_does_not_block_a_new_streak(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "warn")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        common = dict(job_id=ids["job"], printer_id=ids["printer"], camera_id=ids["camera"], defect_class="spaghetti")
        first_id, first_created = await incidents.open_incident(session_factory, reason="detection", **common)
        again_id, again_created = await incidents.open_incident(session_factory, reason="would_pause", announced=True, **common)
        other_id, other_created = await incidents.open_incident(session_factory, reason="detection", **{**common, "defect_class": "layer_shift"})
        await incidents.close_incidents(session_factory, incident_id=first_id, outcome="ignored", decided_by="samuel (web)")
        new_id, new_created = await incidents.open_incident(session_factory, reason="would_pause", announced=True, **common)
        return (first_id, first_created, again_id, again_created, other_id, other_created, new_id, new_created), await incidents_of(session_factory, ids["job"])

    (first_id, first_created, again_id, again_created, other_id, other_created, new_id, new_created), found = with_db(scenario)

    assert (first_created, again_id == first_id, again_created) == (True, True, False)  # the second trigger joined the first
    assert other_created and other_id != first_id  # another class has its own incident
    assert new_created and new_id not in (first_id, other_id)  # the first one was closed: a new streak opens a new one
    assert len(found) == 3
    joined = next(i for i in found if i.id == first_id)
    assert [t["reason"] for t in joined.detail["triggers"]] == ["detection", "would_pause"]
    assert joined.announced_at is not None and joined.status == "closed"


def test_a_lone_detection_opens_an_incident_only_for_an_eligible_class_over_the_threshold_and_only_once(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "warn")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server, layers={})
        async with session_factory() as db:
            camera, model = await db.get(Camera, ids["camera"]), (await db.execute(select(ModelVersion))).scalars().first()
            sent = []
            for number, klass, confidence in ((1, "stringing", 0.95), (2, "spaghetti", 0.40), (3, "spaghetti", 0.80), (4, "spaghetti", 0.90)):
                layer = Layer(job_id=ids["job"], layer_number=number, z_height=Decimal("0.2") * number, telemetry={})
                db.add(layer)
                await db.flush()
                capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"x/{number}.jpg")
                db.add(capture)
                await db.flush()
                detection = Detection(capture_id=capture.id, model_version_id=model.id, has_defect=True, max_confidence=Decimal(str(confidence)),
                                      defect_classes=[klass], raw_output=_raw(confidence, klass))
                db.add(detection)
                await db.flush()
                sent.append({"detection_id": detection.id, "printer_id": ids["printer"], "camera_id": ids["camera"], "has_defect": True})
            await db.commit()
        results = [await incidents.record_detection(session_factory, payload) for payload in sent]
        return results, await incidents_of(session_factory, ids["job"])

    results, found = with_db(scenario)

    assert results[0] is None and results[1] is None  # stringing is cosmetic; spaghetti at 0.40 is under the 0.50 threshold
    assert results[2] is not None and results[3] == results[2]  # the 0.80 opens it, the next one joins it
    (incident,) = found
    assert (incident.reason, incident.defect_class, incident.status) == ("detection", "spaghetti", "open")
    assert [(i["layer"], i["confidence"]) for i in incident.streak] == [(3, 0.8), (4, 0.9)]


def test_printer_state_changes_open_confirm_and_close_incidents(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "warn")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server, layers={})
        common = dict(printer_id=ids["printer"], job_id=ids["job"])
        out = {}
        # a pause with nothing open: an incident of its own, class "pausa"
        await incidents.on_state_change(session_factory, previous_state="printing", new_state="paused", origin="console", order=None, **common)
        out["after_pause"] = await incidents_of(session_factory, ids["job"])
        # resumed from the web: it closes, and says who
        await incidents.on_state_change(
            session_factory, previous_state="paused", new_state="printing", origin="printwatch",
            order={"requested_by": "samuel (web)", "source": "web"}, **common,
        )
        out["after_resume"] = await incidents_of(session_factory, ids["job"])
        # a detection incident is open and the printer pauses: the pause joins it
        await incidents.open_incident(session_factory, reason="would_pause", defect_class="spaghetti", announced=True, camera_id=ids["camera"], **common)
        await incidents.on_state_change(session_factory, previous_state="printing", new_state="paused", origin="external", order=None, **common)
        out["joined"] = await incidents_of(session_factory, ids["job"])
        await incidents.on_state_change(session_factory, previous_state="paused", new_state="cancelled", origin="printwatch",
                                        order={"requested_by": "samuel (web)"}, **common)
        out["after_cancel"] = await incidents_of(session_factory, ids["job"])
        await incidents.open_incident(session_factory, reason="would_pause", defect_class="spaghetti", announced=True, camera_id=ids["camera"], **common)
        await incidents.on_state_change(session_factory, previous_state="printing", new_state="error", origin="printer", order=None, **common)
        out["after_error"] = await incidents_of(session_factory, ids["job"])
        await incidents.open_incident(session_factory, reason="detection", defect_class="layer_shift", **common)
        await incidents.on_state_change(session_factory, previous_state="printing", new_state="complete", origin="printer", order=None, **common)
        out["after_end"] = await incidents_of(session_factory, ids["job"])
        return out

    out = with_db(scenario)

    (pause,) = out["after_pause"]
    assert (pause.reason, pause.defect_class, pause.status, pause.detail["pause_origin"]) == ("pause", "pausa", "paused", "console")
    assert pause.paused_at is not None and pause.mode == "warn"
    (resumed,) = out["after_resume"]
    assert (resumed.status, resumed.outcome, resumed.decided_by) == ("closed", "resumed", "samuel (web)")

    assert len(out["joined"]) == 2 and out["joined"][1].status == "paused" and out["joined"][1].reason == "would_pause"
    assert out["joined"][1].detail["pause_origin"] == "external"
    assert (out["after_cancel"][1].outcome, out["after_cancel"][1].decided_by) == ("cancelled", "samuel (web)")
    assert out["after_error"][2].outcome == "error"
    assert (out["after_end"][3].outcome, out["after_end"][3].decided_by) == ("ignored", None)
    assert out["after_end"][3].detail["closing"] == {"reason": "job_ended"}


# ------------------------------------------------------------------ API

def test_api_lists_reads_labels_and_dismisses_incidents(mock_server, with_db, monkeypatch):
    prepare(monkeypatch, "warn")

    async def scenario(session_factory):
        ids = await seed(session_factory, mock_server)
        manager = auto_pause.AutoPauseManager()
        await manager.check_spaghetti_streak(session_factory, ids["job"], ids["camera"], ids["printer"])
        async with session_factory() as db:
            admin = User(username=f"adm-{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.local", hashed_password="x", role=UserRole.admin)
            viewer = User(username=f"vw-{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.local", hashed_password="x", role=UserRole.viewer)
            db.add_all([admin, viewer])
            await db.commit()
            # a printer event after the incident: it belongs on the timeline
        incident_id = (await incidents_of(session_factory, ids["job"]))[0].id

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        results = {}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                app.dependency_overrides[get_current_user] = lambda: viewer
                results["viewer_list"] = await client.get("/api/v1/incidents")
                results["viewer_label"] = await client.post(f"/api/v1/incidents/{incident_id}/label", json={"label": "correct"})
                app.dependency_overrides[get_current_user] = lambda: admin
                app.dependency_overrides[require_admin] = lambda: admin
                results["unclosed"] = await client.get("/api/v1/incidents", params={"state": "unclosed"})
                results["bad_state"] = await client.get("/api/v1/incidents", params={"state": "weird"})
                results["by_printer"] = await client.get(f"/api/v1/printers/{ids['printer']}/incidents")
                results["by_job"] = await client.get(f"/api/v1/print-jobs/{ids['job']}/incidents")
                results["detail"] = await client.get(f"/api/v1/incidents/{incident_id}")
                results["missing"] = await client.get("/api/v1/incidents/99999")
                results["label"] = await client.post(f"/api/v1/incidents/{incident_id}/label", json={"label": "false_positive"})
                results["bad_label"] = await client.post(f"/api/v1/incidents/{incident_id}/label", json={"label": "maybe"})
                results["dismiss"] = await client.post(f"/api/v1/incidents/{incident_id}/dismiss")
                results["dismiss_again"] = await client.post(f"/api/v1/incidents/{incident_id}/dismiss")
                results["closed"] = await client.get("/api/v1/incidents", params={"state": "closed"})
        finally:
            app.dependency_overrides.clear()
        return ids, incident_id, admin.username, results

    ids, incident_id, admin_name, results = with_db(scenario)

    assert results["viewer_list"].status_code == 200  # reading is for everyone signed in
    assert results["viewer_label"].status_code == 403  # labelling is for administrators
    assert [i["id"] for i in results["unclosed"].json()] == [incident_id]
    assert results["bad_state"].status_code == 422 and results["missing"].status_code == 404
    assert results["by_printer"].json()[0]["job_file_name"] == "cubo_PETG_2m28s.gcode"
    assert [i["id"] for i in results["by_job"].json()] == [incident_id]

    detail = results["detail"].json()
    assert detail["reason"] == "would_pause" and detail["report_url"] == f"/api/v1/print-jobs/{ids['job']}/report.pdf"
    assert [d["layer_number"] for d in detail["detections"]] == [7, 8, 9]
    last = detail["detections"][-1]
    assert last["confidence"] == 0.92 and last["image_url"].startswith("/api/v1/layer-captures/") and last["image_url"].endswith("/thumbnail")
    assert last["boxes"] == [{"class_name": "spaghetti", "confidence": 0.92, "x1": 0.2, "y1": 0.3, "x2": 0.4, "y2": 0.6}]
    assert any(e["event_type"] == "auto_pause.would_pause" for e in detail["events"])
    assert detail["chain"]["ok"] is True and detail["job"]["file_name"] == "cubo_PETG_2m28s.gcode"
    assert detail["telemetry_snapshot"]["sample"]["extruder_temp"] == 249.5 and detail["telemetry_at_pause"] is None

    assert results["label"].json()["label"] == "false_positive" and results["label"].json()["labeled_by"] == admin_name
    assert results["bad_label"].status_code == 422
    dismissed = results["dismiss"].json()
    assert (dismissed["status"], dismissed["outcome"], dismissed["decided_by"]) == ("closed", "ignored", f"{admin_name} (web)")
    assert results["dismiss_again"].status_code == 409
    assert [i["id"] for i in results["closed"].json()] == [incident_id]


def test_boxes_are_placed_on_the_whole_frame_even_when_the_model_saw_only_a_region():
    full = boxes_on_frame({"detections": [{"class": "spaghetti", "confidence": 0.9, "box": [0.1, 0.2, 0.3, 0.4]}]})
    assert full == [{"class_name": "spaghetti", "confidence": 0.9, "x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}]  # an older record: the whole frame
    region = boxes_on_frame({
        "detections": [{"class": "spaghetti", "confidence": 0.7, "box": [0.0, 0.0, 1.0, 1.0]}],
        "frame": {"width": 1000, "height": 500, "roi": {"x": 500, "y": 250, "w": 500, "h": 250}},
    })
    assert region == [{"class_name": "spaghetti", "confidence": 0.7, "x1": 0.5, "y1": 0.5, "x2": 1.0, "y2": 1.0}]
