"""The order PrintWatch sends is written to the event log BEFORE the state change it causes, so the change is
attributed to PrintWatch even when the printer only answers the request long after changing state (the Creality Hi
changes to `paused` within a second and answers when its PAUSE macro ends, ~9 s later; a resume answers 45 to 65 s
later). On 2026-10-09 the order was noted when the answer came and the web's pause was logged as `external`."""

import asyncio
import contextlib
import time

from sqlalchemy import select

from app.db.models import IntegrationType, Printer, PrinterEvent
from app.integrations.moonraker import command_log
from app.integrations.moonraker.client import send_print_action
from app.integrations.moonraker.listener import run_moonraker_listener
from app.services.printer_events import verify_chain
from tests.test_moonraker_listener import _FakeRedis, _wait_for


async def _printer(session_factory, mock_server) -> int:
    async with session_factory() as db:
        printer = Printer(name="Simulada", octoprint_url=mock_server, octoprint_api_key_encrypted="",
                          integration_type=IntegrationType.moonraker)
        db.add(printer)
        await db.commit()
        return printer.id


async def _events(session_factory, printer_id) -> list[PrinterEvent]:
    async with session_factory() as db:
        return list((await db.execute(
            select(PrinterEvent).where(PrinterEvent.printer_id == printer_id).order_by(PrinterEvent.id))).scalars().all())


def test_a_pause_answered_late_is_logged_before_the_state_change_and_attributed_to_printwatch(
    mock_server, mock_moonraker, with_db
):
    import httpx

    mock_moonraker.pause_seconds = 2.5  # the printer changes state at once and answers 2.5 s later

    async def scenario(session_factory):
        command_log._commands.clear()
        printer_id = await _printer(session_factory, mock_server)
        listener = asyncio.create_task(run_moonraker_listener(printer_id, session_factory, _FakeRedis()))
        try:
            async def connected():
                return bool(await _events(session_factory, printer_id))

            await _wait_for(connected, 10, "the listener to connect")
            async with httpx.AsyncClient() as client:
                (await client.post(f"{mock_server}/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
            await asyncio.sleep(2)
            await send_print_action(mock_server, "pause", requested_by="tester (web)")
            await asyncio.sleep(1.5)  # one sampler tick after the answer
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener
        async with session_factory() as db:
            chain = await verify_chain(db, printer_id)
        return await _events(session_factory, printer_id), chain

    events, chain = with_db(scenario)

    order = next(e for e in events if e.event_type == "printwatch_command" and e.detail["action"] == "pause")
    paused = next(e for e in events if e.event_type == "state_changed" and e.value_after == "paused")
    assert order.id < paused.id  # the order reads before the pause it caused
    assert order.detail["ok"] is None  # written when sent, before the printer answered
    assert paused.origin == "printwatch"
    assert paused.detail["printwatch_order"]["requested_by"] == "tester (web)"
    assert chain["ok"] is True


def test_an_order_that_fails_after_being_logged_gets_a_second_entry(mock_server, with_db):
    async def scenario(session_factory):
        command_log._commands.clear()
        printer_id = await _printer(session_factory, mock_server)
        listener = asyncio.create_task(run_moonraker_listener(printer_id, session_factory, _FakeRedis()))
        try:
            async def connected():
                return bool(await _events(session_factory, printer_id))

            await _wait_for(connected, 10, "the listener to connect")
            command = command_log.begin(mock_server, "resume", "tester (web)")

            async def order_logged():
                return any(e.event_type == "printwatch_command" for e in await _events(session_factory, printer_id))

            await _wait_for(order_logged, 5, "the order to be logged")
            command_log.finish(command, ok=False, error="ReadTimeout: ")

            async def failure_logged():
                found = [e for e in await _events(session_factory, printer_id) if e.event_type == "printwatch_command"]
                return len(found) == 2

            await _wait_for(failure_logged, 5, "the failure to be logged")
            await asyncio.sleep(2.2)  # two more ticks: the failure must not be written again
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener
        async with session_factory() as db:
            chain = await verify_chain(db, printer_id)
        return await _events(session_factory, printer_id), chain

    events, chain = with_db(scenario)

    commands = [e for e in events if e.event_type == "printwatch_command"]
    assert len(commands) == 2
    assert commands[0].detail["ok"] is None and not commands[0].detail.get("followup")
    assert commands[1].detail["ok"] is False and commands[1].detail["followup"] is True
    assert commands[1].detail["error"] == "ReadTimeout: "
    assert chain["ok"] is True


def test_the_attribution_window_outlasts_a_slow_resume():
    from app.integrations.moonraker import listener

    assert listener._COMMAND_ATTRIBUTION_SECONDS >= 90  # a real resume changed the state 65 s after the order
    assert time.monotonic() > 0
