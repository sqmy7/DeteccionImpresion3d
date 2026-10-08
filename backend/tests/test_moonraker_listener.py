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
    assert all(layer.telemetry and layer.telemetry["extruder_target"] == 240.0 for layer in layers)
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
