"""The bed-map API against the test database: calibrate a camera with the corners the simulated
camera sees, then place detections made on top of the parts with the bed at other positions."""

import uuid
from decimal import Decimal

import httpx

from app.api.deps import get_current_user, require_admin
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
    User,
    UserRole,
)
from app.db.session import get_db
from app.main import app

WIDTH, HEIGHT = 640, 480
BED = [(0.0, 0.0), (260.0, 0.0), (260.0, 260.0), (0.0, 260.0)]
GEOMETRY = {
    "axis_minimum": [-2.0, -2.0, -2.0, 0.0],
    "axis_maximum": [260.0, 260.0, 300.0, 0.0],
    "bed_mesh": None,
    "objects": [
        {"name": "BOX_1", "center": [95.0, 130.0], "polygon": [[70, 105], [120, 105], [120, 155], [70, 155]]},
        {"name": "BOX_2", "center": [165.0, 130.0], "polygon": [[140, 105], [190, 105], [190, 155], [140, 155]]},
    ],
}


def _box_around(u: float, v: float) -> list[float]:
    return [u - 0.02, v - 0.02, u + 0.02, v + 0.02]


def test_calibrate_then_place_defects_on_the_bed(mock_moonraker, with_db):
    def seen(x: float, y: float, z: float, toolhead_y: float) -> tuple[float, float]:
        u, v = mock_moonraker.camera_project(x, y, z, toolhead_y)
        return u / WIDTH, v / HEIGHT

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
            model = ModelVersion(name=f"test-{uuid.uuid4().hex[:6]}", file_path="test.onnx", classes=["spaghetti"])
            job = PrintJob(printer_id=printer.id, file_name="mock_box.gcode", geometry=GEOMETRY)
            db.add_all([camera, model, job])
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_admin] = lambda: user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                crossed = await client.post(
                    f"/api/v1/cameras/{camera.id}/calibration",
                    json={"image_points": [[0.1, 0.9], [0.9, 0.1], [0.9, 0.9], [0.1, 0.1]], "image_width": WIDTH,
                          "image_height": HEIGHT, "reference_y": 75.0},
                )
                no_y = await client.post(
                    f"/api/v1/cameras/{camera.id}/calibration",
                    json={"image_points": [list(seen(x, y, 0.0, 75.0)) for x, y in BED], "image_width": WIDTH,
                          "image_height": HEIGHT},
                )
                created = await client.post(
                    f"/api/v1/cameras/{camera.id}/calibration",
                    json={"image_points": [list(seen(x, y, 0.0, 75.0)) for x, y in BED], "image_width": WIDTH,
                          "image_height": HEIGHT, "bed_moves_in_image": True, "reference_y": 75.0},
                )

                # Captured after calibrating: one defect on top of BOX_1 with the bed still, one on
                # BOX_2 with the bed sliding fast, and one stored in the early pixel box format.
                async with session_factory() as db:
                    for number, z, head_y, speed, point, frame in (
                        (10, 2.0, 150.0, 0.0, (95.0, 130.0), {"width": WIDTH, "height": HEIGHT,
                                                               "roi": {"x": 0, "y": 0, "w": WIDTH, "h": HEIGHT}}),
                        (20, 4.0, 30.0, 250.0, (165.0, 130.0), None),
                    ):
                        layer = Layer(
                            job_id=job.id, layer_number=number, z_height=Decimal(str(z)),
                            telemetry={"x": 100.0, "y": head_y, "z": z, "velocity": speed, "current_object": "BOX_1"},
                        )
                        db.add(layer)
                        await db.flush()
                        capture = LayerCapture(layer_id=layer.id, camera_id=camera.id, image_path=f"{number}.jpg")
                        db.add(capture)
                        await db.flush()
                        raw = {"detections": [{"class": "spaghetti", "confidence": 0.8,
                                               "box": _box_around(*seen(*point, z, head_y))}]}
                        if frame:
                            raw["frame"] = frame
                        if number == 20:
                            raw["detections"].append({"class": "spaghetti", "confidence": 0.5, "box": [120, 80, 200, 160]})
                        db.add(Detection(capture_id=capture.id, model_version_id=model.id, has_defect=True,
                                         max_confidence=Decimal("0.8"), defect_classes=["spaghetti"], raw_output=raw))
                    await db.commit()

                bed_map = await client.get(f"/api/v1/print-jobs/{job.id}/bed-map")
                heatmap = await client.get(f"/api/v1/printers/{printer.id}/bed-heatmap")
                latest = await client.get(f"/api/v1/cameras/{camera.id}/calibration")
        finally:
            app.dependency_overrides.clear()
        return crossed, no_y, created, bed_map, heatmap, latest

    crossed, no_y, created, bed_map, heatmap, latest = with_db(scenario)

    assert crossed.status_code == 422
    assert no_y.status_code == 422  # the bed moves in the image and nobody said where it was
    assert created.status_code == 201, created.text
    calibration = created.json()
    assert calibration["warnings"] == []
    assert calibration["bed_points"] == [[0.0, 0.0], [260.0, 0.0], [260.0, 260.0], [0.0, 260.0]]
    assert abs(calibration["focal_px"] - mock_moonraker.CAMERA_FOCAL_PX) < 6
    assert latest.json()["id"] == calibration["id"]

    body = bed_map.json()
    assert body["skipped_boxes"] == 1  # the early pixel-format box
    still, moving = body["defects"]
    assert abs(still["x"] - 95.0) < 1.5 and abs(still["y"] - 130.0) < 1.5
    assert still["reliable"] and still["object"] == "BOX_1"
    assert still["head"] == {"x": 100.0, "y": 150.0, "z": 2.0}
    assert abs(moving["x"] - 165.0) < 1.5 and abs(moving["y"] - 130.0) < 1.5
    assert not moving["reliable"] and moving["uncertainty_mm"] >= 60

    grid = heatmap.json()
    assert (grid["located"], grid["unreliable"], grid["skipped_boxes"]) == (1, 1, 1)
    assert grid["counts"][130 // 20][95 // 20] == 1
    assert len(grid["counts"]) == 13 and len(grid["counts"][0]) == 13


def test_calibrating_with_a_known_focal_keeps_it_and_reports_the_marks(mock_moonraker, with_db):
    """A fixed focal is stored, comes back as such when the calibration is read again (the stored row is
    all there is: no new column), is rejected when implausible, and a mark far off its corner is
    flagged with the error of each mark."""

    known = 520.0  # not the simulator's 560: a known focal equal to the estimate would read back as estimated

    def marks(offset_third: tuple[float, float] = (0.0, 0.0)) -> list[list[float]]:
        points = [list(mock_moonraker.camera_project(x, y, 0.0, 75.0)) for x, y in BED]
        points = [[u / WIDTH, v / HEIGHT] for u, v in points]
        points[2][0] += offset_third[0]
        points[2][1] += offset_third[1]
        return points

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
            db.add(camera)
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_admin] = lambda: user
        base = {"image_width": WIDTH, "image_height": HEIGHT, "bed_moves_in_image": True, "reference_y": 75.0}
        url = f"/api/v1/cameras/{camera.id}/calibration"
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                estimated = await client.post(url, json={**base, "image_points": marks()})
                absurd = await client.post(url, json={**base, "image_points": marks(), "focal_px": 5.0})
                fixed = await client.post(
                    url, json={**base, "image_points": marks(), "focal_px": known}
                )
                off = await client.post(
                    url,
                    json={**base, "image_points": marks((-0.10, 0.09)), "focal_px": known},
                )
                listed = await client.get(f"/api/v1/cameras/{camera.id}/calibrations")
        finally:
            app.dependency_overrides.clear()
        return estimated, absurd, fixed, off, listed

    estimated, absurd, fixed, off, listed = with_db(scenario)

    assert estimated.status_code == 201 and estimated.json()["focal_source"] == "estimated"
    assert absurd.status_code == 422 and "focal" in absurd.json()["detail"]

    assert fixed.status_code == 201, fixed.text
    body = fixed.json()
    assert body["focal_source"] == "fixed" and body["focal_px"] == known
    assert "focal_fixed" in body["notes"] and body["warnings"] == []
    assert len(body["marks"]) == 4 and all(mark["error_mm"] < 5.0 for mark in body["marks"])
    assert body["typical_focal_px"] == 494.0  # the C922's focal at 640x480

    flagged = off.json()
    assert "mark_far_from_corner" in flagged["warnings"]
    errors = [mark["error_mm"] for mark in flagged["marks"]]
    assert errors.index(max(errors)) == 2

    # Read again from the stored row: the fixed focal is still fixed, and the list carries the errors.
    again = {row["id"]: row for row in listed.json()}
    assert again[body["id"]]["focal_source"] == "fixed"
    assert again[body["id"]]["focal_px"] == known
    assert again[estimated.json()["id"]]["focal_source"] == "estimated"
    assert "mark_far_from_corner" in again[flagged["id"]]["warnings"]
