import asyncio
import contextlib
import json
import time

import httpx
from sqlalchemy import func, select

from app.db.models import IntegrationType, JobStatus, Layer, Printer, PrinterEvent, PrintJob, TelemetrySample
from app.integrations.moonraker.client import send_print_action
from app.integrations.moonraker.listener import run_moonraker_listener
from app.services.printer_events import verify_chain


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, json.loads(message)))
        return 1


async def _wait_for(condition, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not await condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.2)


def test_listener_records_layers_telemetry_and_attributed_events(mock_server, with_db):
    """End to end against the simulated printer: a print with a pause and a resume sent through
    PrintWatch's own client, so the event log must attribute both to PrintWatch."""

    async def scenario(session_factory):
        async with session_factory() as db:
            printer = Printer(
                name="Simulada",
                octoprint_url=mock_server,
                octoprint_api_key_encrypted="",
                integration_type=IntegrationType.moonraker,
            )
            db.add(printer)
            await db.commit()
            printer_id = printer.id

        async def job_state():
            async with session_factory() as db:
                return (await db.execute(select(PrintJob.status).where(PrintJob.printer_id == printer_id))).scalar()

        async def layers_recorded():
            async with session_factory() as db:
                return await db.scalar(select(func.count()).select_from(Layer))

        redis = _FakeRedis()
        listener = asyncio.create_task(run_moonraker_listener(printer_id, session_factory, redis))
        try:
            async def connected():
                async with session_factory() as db:
                    return await db.scalar(select(func.count()).select_from(PrinterEvent)) > 0

            await _wait_for(connected, 10, "the listener to connect")
            async with httpx.AsyncClient() as client:
                (await client.post(f"{mock_server}/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()

            async def first_layer_done():
                return (await layers_recorded() or 0) >= 2

            await _wait_for(first_layer_done, 20, "two layers")
            await send_print_action(mock_server, "pause", requested_by="tester (web)")
            await asyncio.sleep(1.5)
            await send_print_action(mock_server, "resume", requested_by="tester (web)")

            async def finished():
                return await job_state() == JobStatus.completed

            await _wait_for(finished, 30, "the print to finish")
            await asyncio.sleep(1.2)  # one more sampler tick flushes the last samples
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener

        async with session_factory() as db:
            layers = (await db.execute(select(Layer).order_by(Layer.layer_number))).scalars().all()
            samples = await db.scalar(select(func.count()).select_from(TelemetrySample))
            events = (await db.execute(select(PrinterEvent).order_by(PrinterEvent.id))).scalars().all()
            chain = await verify_chain(db, printer_id)
        return layers, samples, events, chain, redis.published

    layers, samples, events, chain, published = with_db(scenario)

    assert [layer.layer_number for layer in layers] == [1, 2, 3, 4]
    # The simulated file programs 235 °C from layer 2 on ("M104 S235").
    assert [layer.telemetry["extruder_target"] for layer in layers] == [240.0, 235.0, 235.0, 235.0]
    assert all(layer.telemetry.get("current_object") in ("BOX_1", "BOX_2", None) for layer in layers)
    assert [payload["layer_number"] for _, payload in published] == [1, 2, 3, 4]
    assert samples >= 8  # 4 layers x 2 s, plus heating and the pause

    summary = [(event.event_type, event.value_before, event.value_after, event.origin) for event in events]
    assert summary[0] == ("monitor_connected", None, "standby", "monitor")
    assert ("state_changed", "standby", "printing", "external") in summary
    assert ("printwatch_command", None, None, "printwatch") in summary
    assert ("state_changed", "printing", "paused", "printwatch") in summary
    assert ("state_changed", "paused", "printing", "printwatch") in summary
    assert ("state_changed", "printing", "complete", "printer") in summary

    pause = next(event for event in events if event.value_after == "paused")
    assert pause.detail["printwatch_order"]["requested_by"] == "tester (web)"
    opened = next(event for event in events if event.value_after == "printing" and event.value_before == "standby")
    assert opened.detail["job_opened"] == opened.print_job_id
    assert chain["ok"] is True


def test_job_found_finished_on_connect_ends_at_its_last_layer(mock_server, with_db):
    """The print finished while PrintWatch wasn't listening: the job must not end "now"."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    async def scenario(session_factory):
        async with httpx.AsyncClient(base_url=mock_server) as client:
            (await client.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
            deadline = time.monotonic() + 40
            while True:
                state = (await client.get("/printer/objects/query", params={"print_stats": "state"})).json()
                if state["result"]["status"]["print_stats"]["state"] == "complete":
                    break
                assert time.monotonic() < deadline, "the simulated print did not finish"
                await asyncio.sleep(0.5)

        last_layer_at = datetime.now(timezone.utc) - timedelta(hours=3)
        async with session_factory() as db:
            printer = Printer(name="Simulada", octoprint_url=mock_server, octoprint_api_key_encrypted="", integration_type=IntegrationType.moonraker)
            db.add(printer)
            await db.flush()
            job = PrintJob(printer_id=printer.id, file_name="mock_box.gcode", started_at=last_layer_at - timedelta(hours=1))
            db.add(job)
            await db.flush()
            db.add_all(
                [
                    Layer(job_id=job.id, layer_number=1, z_height=Decimal("0.2"), detected_at=last_layer_at - timedelta(minutes=30)),
                    Layer(job_id=job.id, layer_number=2, z_height=Decimal("0.4"), detected_at=last_layer_at),
                ]
            )
            await db.commit()
            printer_id, job_id = printer.id, job.id

        listener = asyncio.create_task(run_moonraker_listener(printer_id, session_factory, _FakeRedis()))
        try:
            async def closed():
                async with session_factory() as db:
                    return (await db.get(PrintJob, job_id)).status != JobStatus.running

            await _wait_for(closed, 15, "the job to be closed")
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener

        async with session_factory() as db:
            job = await db.get(PrintJob, job_id)
            connected = (await db.execute(select(PrinterEvent).where(PrinterEvent.event_type == "monitor_connected"))).scalar_one()
        return job, connected, last_layer_at

    job, connected, last_layer_at = with_db(scenario)

    assert job.status == JobStatus.completed
    assert job.ended_at == last_layer_at
    assert connected.detail["closed_on_connect"] is True and connected.print_job_id == job.id


def test_interventions_are_attributed_to_console_file_printwatch_or_external(mock_server, with_db, monkeypatch):
    """A print with one change of every kind: programmed in the file (directly and through the
    START_PRINT/END_PRINT macros), typed in the console, made on the printer's screen, and a pause
    by PrintWatch resumed from the console."""
    from app.integrations.moonraker import interventions

    monkeypatch.setattr(interventions, "_CONSOLE_POLL_SECONDS", 0.5)
    monkeypatch.setattr(interventions, "_CONSOLE_WAIT_SECONDS", 1.5)

    async def scenario(session_factory):
        async with session_factory() as db:
            printer = Printer(
                name="Simulada",
                octoprint_url=mock_server,
                octoprint_api_key_encrypted="",
                integration_type=IntegrationType.moonraker,
            )
            db.add(printer)
            await db.commit()
            printer_id = printer.id

        async def events():
            async with session_factory() as db:
                return (await db.execute(select(PrinterEvent).order_by(PrinterEvent.id))).scalars().all()

        async def has_event(event_type, after=None):
            return any(e.event_type == event_type and (after is None or e.value_after == after) for e in await events())

        listener =asyncio.create_task(run_moonraker_listener(printer_id, session_factory, _FakeRedis()))
        try:
            async with httpx.AsyncClient(base_url=mock_server) as client:

                async def console(script):
                    (await client.post("/printer/gcode/script", params={"script": script})).raise_for_status()

                await _wait_for(lambda: has_event("monitor_connected"), 10, "the listener to connect")
                (await client.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()

                async def at_layer_3():
                    async with session_factory() as db:
                        return ((await db.scalar(select(func.max(Layer.layer_number)))) or 0) >= 3

                await _wait_for(at_layer_3, 30, "layer 3")
                await console("M220 S80")
                await _wait_for(lambda: has_event("speed_factor_changed"), 10, "the speed change")
                (await client.post("/mock/screen", params={"script": "M140 S75"})).raise_for_status()
                await console("EXCLUDE_OBJECT NAME=BOX_2")
                await console("SET_GCODE_OFFSET Z_ADJUST=0.05")
                await _wait_for(lambda: has_event("z_offset_changed"), 10, "the Z offset change")
                await send_print_action(mock_server, "pause", requested_by="tester (web)")
                await _wait_for(lambda: has_event("state_changed", "paused"), 10, "the pause")
                await console("RESUME")
                await _wait_for(lambda: has_event("state_changed", "complete"), 60, "the print to finish")
                await asyncio.sleep(3)  # let the last pending changes resolve
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener

        async with session_factory() as db:
            chain = await verify_chain(db, printer_id)
        return await events(), chain

    events, chain = with_db(scenario)
    log = [(e.event_type, e.field, e.value_before, e.value_after, e.origin, (e.detail or {}).get("via_macro")) for e in events]

    def find(event_type, after, field=None):
        matches = [entry for entry in log if entry[0] == event_type and entry[3] == after and (field is None or entry[1] == field)]
        assert matches, f"no {event_type} -> {after!r} in {log}"
        return matches[0]

    assert find("target_changed", 240.0, "extruder.target")[4:] == ("gcode_file", "START_PRINT")
    assert find("target_changed", 70.0, "heater_bed.target")[4:] == ("gcode_file", "START_PRINT")
    assert find("target_changed", 235.0)[4:] == ("gcode_file", None)
    assert find("console_command", "M220 S80")[4] == "console"
    assert find("speed_factor_changed", 0.8)[4] == "console"
    assert find("target_changed", 75.0)[4] == "external"  # the screen leaves no trace
    assert find("object_excluded", "BOX_2")[4] == "console"
    assert find("z_offset_changed", 0.05)[4] == "console"
    assert find("state_changed", "paused")[4] == "printwatch"
    assert find("console_command", "RESUME")[4] == "console"
    assert find("state_changed", "printing", "print_stats.state") in log
    resumed = [entry for entry in log if entry[0] == "state_changed" and entry[2] == "paused"]
    assert resumed[0][4] == "console"
    assert find("target_changed", 0.0, "extruder.target")[4:] == ("gcode_file", "END_PRINT")
    assert find("target_changed", 0.0, "heater_bed.target")[4:] == ("gcode_file", "END_PRINT")
    assert find("state_changed", "complete")[4] == "printer"
    assert not [entry for entry in log if entry[0] == "fan_changed"]  # all programmed in the file
    # Only the print start (Moonraker's start API leaves no console trace) and the screen change
    # have no evidence behind them.
    assert {(entry[0], entry[3]) for entry in log if entry[4] == "external"} == {
        ("state_changed", "printing"),
        ("target_changed", 75.0),
    }
    assert chain["ok"] is True
