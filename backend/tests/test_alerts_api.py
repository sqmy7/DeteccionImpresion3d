"""The alert list says which job and layer raised each alert, and filters by job."""

import uuid
from decimal import Decimal

import httpx

from app.api.deps import get_current_user, require_admin
from app.db.models import (
    Alert,
    AlertSeverity,
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
    User,
    UserRole,
)
from app.db.session import get_db
from app.main import app


def test_alerts_carry_their_job_and_layer(with_db):
    async def scenario(session_factory):
        async with session_factory() as db:
            user = User(
                username=f"tester-{uuid.uuid4().hex[:8]}",
                email=f"{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="x",
                role=UserRole.admin,
            )
            printer = Printer(
                name="Simulada", octoprint_url="http://mock", octoprint_api_key_encrypted="",
                integration_type=IntegrationType.moonraker,
            )
            db.add_all([user, printer])
            await db.flush()
            camera = Camera(
                printer_id=printer.id, name="C922", source_type=CameraSourceType.usb, source_uri="0",
                role=CameraRole.primary,
            )
            model = ModelVersion(name=f"test-{uuid.uuid4().hex[:6]}", file_path="test.onnx", classes=["under_extrusion"])
            jobs = [PrintJob(printer_id=printer.id, file_name=name) for name in ("pieza_a.gcode", "pieza_b.gcode")]
            db.add_all([camera, model, *jobs])
            await db.flush()
            for job, number in zip(jobs, (28, 7)):
                layer = Layer(job_id=job.id, layer_number=number, z_height=Decimal("1.0"))
                db.add(layer)
                await db.flush()
                capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"{number}.jpg")
                db.add(capture)
                await db.flush()
                detection = Detection(capture_id=capture.id, model_version_id=model.id, has_defect=True,
                                      max_confidence=Decimal("0.6"), defect_classes=["under_extrusion"], raw_output={})
                db.add(detection)
                await db.flush()
                db.add(Alert(detection_id=detection.id, printer_id=printer.id, severity=AlertSeverity.critical))
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_admin] = lambda: user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                every = await client.get("/api/v1/alerts")
                first_job = await client.get("/api/v1/alerts", params={"job_id": jobs[0].id})
        finally:
            app.dependency_overrides.clear()
        return jobs, every, first_job

    jobs, every, first_job = with_db(scenario)

    assert every.status_code == 200, every.text
    placed = {(item["print_job_id"], item["layer_number"], item["file_name"]) for item in every.json()}
    assert placed == {(jobs[0].id, 28, "pieza_a.gcode"), (jobs[1].id, 7, "pieza_b.gcode")}
    assert [(item["print_job_id"], item["layer_number"]) for item in first_job.json()] == [(jobs[0].id, 28)]
