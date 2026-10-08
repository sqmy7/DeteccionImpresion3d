import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
    PrintJob,
    TelemetrySample,
)
from app.services.analytics import analytics_summary
from app.services.printer_events import EventOrigin, record_event


def test_summary_counts_outcomes_defects_interventions_and_temperature_error(with_db):
    now = datetime.now(timezone.utc)

    async def scenario(session_factory):
        async with session_factory() as db:
            printer = Printer(name="P", octoprint_url="http://x", octoprint_api_key_encrypted="", integration_type=IntegrationType.moonraker)
            db.add(printer)
            await db.flush()
            cameras = [
                Camera(printer_id=printer.id, name=f"c{role.value}", source_type=CameraSourceType.usb, source_uri="0", role=role)
                for role in (CameraRole.primary, CameraRole.secondary)
            ]
            model = ModelVersion(name=f"m-{uuid.uuid4().hex[:6]}", file_path="m.onnx", classes=[])
            completed = PrintJob(printer_id=printer.id, file_name="a.gcode", status=JobStatus.completed,
                                 started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
            failed = PrintJob(printer_id=printer.id, file_name="b.gcode", status=JobStatus.failed,
                              started_at=now - timedelta(minutes=30), ended_at=now - timedelta(minutes=10))
            running = PrintJob(printer_id=printer.id, file_name="c.gcode", status=JobStatus.running, started_at=now - timedelta(minutes=5))
            db.add_all([*cameras, model, completed, failed, running])
            await db.flush()

            async def layer(job, number, *detections):
                row = Layer(job_id=job.id, layer_number=number, z_height=Decimal("0.2") * number)
                db.add(row)
                await db.flush()
                for camera, has_defect, classes in detections:
                    capture = LayerCapture(layer_id=row.id, camera_id=camera.id, image_path=f"{job.id}_{number}_{camera.id}.jpg")
                    db.add(capture)
                    await db.flush()
                    db.add(Detection(capture_id=capture.id, model_version_id=model.id, has_defect=has_defect,
                                     defect_classes=classes, raw_output={"detections": []}))

            primary, secondary = cameras
            await layer(completed, 1, (primary, False, []))
            # Both cameras saw stringing on layer 2: still one defective layer, one stringing layer.
            await layer(completed, 2, (primary, True, ["stringing"]), (secondary, True, ["stringing"]))
            # Informational classes don't count as defects.
            await layer(completed, 3, (primary, True, ["spaghetti", "blob_over_extrusion"]))
            await layer(completed, 4, (primary, True, ["blob_over_extrusion"]))
            await layer(failed, 1, (primary, False, []))
            await layer(failed, 2, (primary, False, []))

            start = now - timedelta(hours=2)
            for second, (layer_number, nozzle, filament) in enumerate([(0, 100.0, 0.0), (1, 239.0, 500.0), (2, 241.0, 1500.0)]):
                db.add(TelemetrySample(print_job_id=completed.id, ts=start + timedelta(seconds=second), layer_number=layer_number,
                                       extruder_temp=nozzle, extruder_target=240.0, bed_temp=70.0, bed_target=70.0,
                                       filament_used=filament))
            await db.commit()
            ids = (printer.id, completed.id, failed.id, running.id)

        for origin in (EventOrigin.CONSOLE, EventOrigin.CONSOLE, EventOrigin.EXTERNAL):
            await record_event(session_factory, ids[0], "target_changed", origin, job_id=ids[1])
        await record_event(session_factory, ids[0], "speed_factor_changed", EventOrigin.EXTERNAL, job_id=ids[2])
        await record_event(session_factory, ids[0], "state_changed", EventOrigin.PRINTWATCH, job_id=ids[2])

        async with session_factory() as db:
            everything = await analytics_summary(db, ids[0], None, now)
            recent = await analytics_summary(db, ids[0], now - timedelta(hours=1), now)
        return ids, everything, recent

    (printer_id, completed_id, failed_id, _), summary, recent = with_db(scenario)

    totals = summary["totals"]
    assert totals["jobs"] == 3
    assert totals["success_rate"] == 0.5  # 1 completed of 2 finished; the running one doesn't count
    assert totals["layers"] == 6 and totals["layers_with_defect"] == 2
    assert totals["interventions"] == 4  # the state change is not an intervention
    assert summary["defects_by_class"] == {"stringing": 1, "spaghetti": 1}
    assert summary["interventions_by_origin"] == {"console": 2, "external": 2}
    assert summary["status_counts"] == {"completed": 1, "failed": 1, "running": 1}

    job = next(row for row in summary["jobs"] if row["id"] == completed_id)
    assert job["layers_with_defect"] == 2 and job["defect_rate"] == 0.5
    assert job["nozzle_error_mean_c"] == 1.0  # heating sample (layer 0) excluded
    assert job["bed_error_mean_c"] == 0.0
    assert job["filament_m"] == 1.5
    assert job["duration_s"] == 3600.0

    assert [row["id"] for row in recent["jobs"]] == [failed_id, summary["jobs"][2]["id"]]
