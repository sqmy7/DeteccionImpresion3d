"""The time a job really printed (the printer's own clock) next to the time PrintWatch followed it."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.api.deps import get_current_user, require_admin
from app.db.models import IntegrationType, JobStatus, Printer, PrintJob, TelemetrySample, User, UserRole
from app.db.session import get_db
from app.main import app

START = datetime(2026, 10, 9, 0, 7, 53, tzinfo=timezone.utc)


def _samples(job_id: int, clock: list[float | None]) -> list[TelemetrySample]:
    return [
        TelemetrySample(
            print_job_id=job_id, ts=START + timedelta(seconds=index), layer_number=index // 5,
            extra=None if value is None else {"print_stats.print_duration": value, "mcu_temp": 39.0},
        )
        for index, value in enumerate(clock)
    ]


def test_jobs_carry_the_printers_print_clock_and_old_ones_do_not(with_db):
    async def scenario(session_factory):
        async with session_factory() as db:
            user = User(username=f"t-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local",
                        hashed_password="x", role=UserRole.admin)
            printer = Printer(name="Simulada", octoprint_url="http://mock", octoprint_api_key_encrypted="",
                              integration_type=IntegrationType.moonraker)
            db.add_all([user, printer])
            await db.flush()
            # Followed from the start: the clock starts later than the job (the nozzle heats first).
            short = PrintJob(printer_id=printer.id, file_name="cubo.gcode", status=JobStatus.completed,
                             started_at=START, ended_at=START + timedelta(seconds=216))
            # Joined late: PrintWatch saw 3 h of a 6 h print, the printer's clock says 6 h.
            late = PrintJob(printer_id=printer.id, file_name="caja.gcode", status=JobStatus.completed,
                            started_at=START, ended_at=START + timedelta(hours=3))
            # Recorded before the clock was kept: no print_duration anywhere.
            old = PrintJob(printer_id=printer.id, file_name="vieja.gcode", status=JobStatus.completed,
                           started_at=START, ended_at=START + timedelta(hours=1))
            empty = PrintJob(printer_id=printer.id, file_name="sin_muestras.gcode", status=JobStatus.failed,
                             started_at=START, ended_at=START + timedelta(minutes=2))
            db.add_all([short, late, old, empty])
            await db.flush()
            db.add_all(_samples(short.id, [None, 0.0, 0.0, 80.5, 162.0, 161.0]))  # the clock never goes back
            db.add_all(_samples(late.id, [0.0, 21660.0, 21659.5]))
            db.add_all(_samples(old.id, [None, None, None]))
            await db.commit()
            ids = {"short": short.id, "late": late.id, "old": old.id, "empty": empty.id}
            printer_id = printer.id

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_admin] = lambda: user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                listed = await client.get(f"/api/v1/printers/{printer_id}/print-jobs")
                one = await client.get(f"/api/v1/print-jobs/{ids['late']}")
        finally:
            app.dependency_overrides.clear()
        return ids, listed, one

    ids, listed, one = with_db(scenario)

    assert listed.status_code == 200 and one.status_code == 200
    by_id = {row["id"]: row for row in listed.json()}
    assert by_id[ids["short"]]["printed_s"] == 162.0  # the largest value, not the last
    assert by_id[ids["late"]]["printed_s"] == 21660.0
    assert by_id[ids["old"]]["printed_s"] is None  # unknown, not zero
    assert by_id[ids["empty"]]["printed_s"] is None
    assert one.json()["printed_s"] == 21660.0 and one.json()["file_name"] == "caja.gcode"
