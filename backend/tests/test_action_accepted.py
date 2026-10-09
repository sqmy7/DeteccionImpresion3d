"""Pause, resume and cancel from the web answer "accepted" without waiting for the printer to finish the order.

The Creality Hi answers the request when its macro has ended: ~9 s after a pause, 45 to 65 s after a resume. With a
10 s limit PrintWatch cut the request off ("ReadTimeout"), the web showed a 502 and the event log said ok:false,
although the printer had done what it was told (2026-10-09, twice). Against the simulated printer, which can hold the
answer back after changing state."""

import asyncio
import time

from app.api.v1 import printers as printers_api
from app.integrations.moonraker import client, command_log
from tests.test_resume_guard import _scenario, _state


def _orders(base_url: str, action: str):
    return [c for c in command_log._commands if c.base_url == base_url and c.action == action]


def test_a_slow_answer_is_accepted_at_once_and_the_order_is_not_marked_failed(with_db, mock_server, mock_moonraker, monkeypatch):
    mock_moonraker.pause_seconds = 2.5  # the printer pauses at once and answers 2.5 s later
    monkeypatch.setattr(printers_api, "ACCEPT_WAIT_SECONDS", 0.4)

    async def steps(client_, printer_id, mock):
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        started = time.monotonic()
        response = await client_.post(f"/api/v1/printers/{printer_id}/pause")
        answered_in = time.monotonic() - started
        right_after = [c.ok for c in _orders(mock_server, "pause")]
        paused = await _state(mock)
        await asyncio.sleep(2.6)  # the printer's answer arrives
        return response, answered_in, right_after, paused, [c.ok for c in _orders(mock_server, "pause")]

    response, answered_in, right_after, paused, later = with_db(_scenario(mock_server, steps))
    assert response.status_code == 202
    assert response.json()["accepted"] is True and response.json()["pending"] is True and response.json()["action"] == "pause"
    assert answered_in < 2.0  # did not wait for the printer's answer
    assert right_after == [None]  # sent, not failed
    assert paused == "paused"
    assert later == [True]


def test_a_quick_refusal_still_reaches_the_user_as_an_error(with_db, mock_server):
    async def steps(client_, printer_id, mock):
        return await client_.post(f"/api/v1/printers/{printer_id}/pause")  # standby: Moonraker answers 400

    response = with_db(_scenario(mock_server, steps))
    assert response.status_code == 502
    assert "pause" in response.json()["detail"]
    assert [c.ok for c in _orders(mock_server, "pause")] == [False]


def test_an_unreachable_printer_is_a_quick_error_not_a_two_minute_wait(with_db):
    async def steps(client_, printer_id, mock):
        started = time.monotonic()
        response = await client_.post(f"/api/v1/printers/{printer_id}/pause")
        return response, time.monotonic() - started

    async def scenario(session_factory):
        return await _scenario("http://127.0.0.1:9", steps)(session_factory)

    response, took = with_db(scenario)
    assert response.status_code == 502
    assert took < 5  # the connection is refused at once; the long limit is for the answer, not for connecting


def test_the_wait_for_the_printers_answer_outlasts_a_real_resume():
    assert client._ANSWER_TIMEOUT_SECONDS >= 90  # a real resume answered after 45 to 65 s
    assert client._CONNECT_TIMEOUT_SECONDS <= 10  # but an unreachable printer is still reported quickly
