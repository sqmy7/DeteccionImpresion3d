"""While a resume is being carried out no second one is accepted. The real printer takes 45 to 65 s to resume and its
state stays `paused` until it ends, so the state check alone let a second click through between the cooldown (20 s)
and the end of the first one. Against the simulated printer with a slow resume (--resume-seconds)."""

import asyncio
import time

from app.api.v1 import printers as printers_api
from app.integrations.moonraker import command_log, print_guard
from tests.test_resume_guard import _resumes_sent, _scenario, _start_and_pause, _state


def _slow(mock_moonraker, monkeypatch, seconds=2.0):
    mock_moonraker.resume_seconds = seconds
    monkeypatch.setattr(printers_api, "ACCEPT_WAIT_SECONDS", 0.2)  # answer "accepted" while the printer works
    monkeypatch.setattr(print_guard, "RESUME_COOLDOWN_SECONDS", 0.0)  # so only the in-progress rule can refuse


def test_a_second_click_while_the_resume_is_running_is_refused(with_db, mock_server, mock_moonraker, monkeypatch):
    _slow(mock_moonraker, monkeypatch)

    async def steps(client, printer_id, mock):
        await _start_and_pause(mock)
        url = f"/api/v1/printers/{printer_id}/resume"
        first = await client.post(url)
        state_meanwhile = await _state(mock)  # still paused: the printer has not finished
        await asyncio.sleep(0.7)
        second = await client.post(url)
        resumes_before_end = _resumes_sent(mock_server)
        await asyncio.sleep(2.0)  # the first one ends
        return first, state_meanwhile, second, resumes_before_end, await _state(mock)

    first, meanwhile, second, sent_before_end, final = with_db(_scenario(mock_server, steps))
    assert first.status_code == 202 and first.json()["pending"] is True
    assert meanwhile == "paused"
    assert second.status_code == 409 and "sigue en curso" in second.json()["detail"]
    assert sent_before_end == 1  # the second never reached the printer
    assert final == "printing"
    assert [c.ok for c in command_log._commands if c.action == "resume"] == [True]  # and the first one succeeded


def test_once_the_resume_ended_a_new_pause_can_be_resumed_again(with_db, mock_server, mock_moonraker, monkeypatch):
    """The rule is about an order still running, not a lock for 90 s: the jam on 2026-10-09 paused the print again
    34 s after a resume and the user must be able to resume it."""
    _slow(mock_moonraker, monkeypatch, seconds=1.0)

    async def steps(client, printer_id, mock):
        await _start_and_pause(mock)
        url = f"/api/v1/printers/{printer_id}/resume"
        first = await client.post(url)
        await asyncio.sleep(1.5)  # the first one ends: printing
        (await mock.post("/printer/print/pause")).raise_for_status()  # paused again
        second = await client.post(url)
        await asyncio.sleep(1.4)
        return first, second, await _state(mock)

    first, second, final = with_db(_scenario(mock_server, steps))
    assert (first.status_code, second.status_code) == (202, 202)
    assert final == "printing"
    assert _resumes_sent(mock_server) == 2


def test_an_order_the_printer_never_answers_stops_blocking_after_the_cap(with_db, mock_server, mock_moonraker, monkeypatch):
    _slow(mock_moonraker, monkeypatch, seconds=2.5)
    monkeypatch.setattr(print_guard, "RESUME_IN_PROGRESS_SECONDS", 0.5)

    async def steps(client, printer_id, mock):
        await _start_and_pause(mock)
        url = f"/api/v1/printers/{printer_id}/resume"
        first = await client.post(url)
        quick = await client.post(url)  # inside the cap: refused
        await asyncio.sleep(0.7)
        late = await client.post(url)  # past the cap and still paused: the check no longer holds it back
        await asyncio.sleep(3.0)
        return first, quick, late

    first, quick, late = with_db(_scenario(mock_server, steps))
    assert (first.status_code, quick.status_code, late.status_code) == (202, 409, 202)
    assert time.monotonic() > 0


def test_an_order_is_in_progress_until_the_printer_answers_it_and_a_failed_one_is_not():
    base_url = "http://printer.test"
    command_log._commands.clear()
    window = print_guard.CANCEL_IN_PROGRESS_SECONDS
    command = command_log.begin(base_url, "cancel", "someone (web)")
    assert command_log.in_progress(base_url, "cancel", window) is not None  # sent, not answered
    assert command_log.in_progress(base_url, "resume", window) is None  # another kind of order
    assert command_log.in_progress("http://other.test", "cancel", window) is None  # another printer
    command_log.finish(command, ok=True)
    assert command_log.in_progress(base_url, "cancel", window) is None  # answered

    failed = command_log.begin(base_url, "cancel", "someone (web)")
    command_log.finish(failed, ok=False, error="ConnectError: ")
    assert command_log.in_progress(base_url, "cancel", window) is None  # a failed order is over (the cooldown covers it)
