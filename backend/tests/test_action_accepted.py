"""Pause, resume and cancel from the web answer "accepted" without waiting for the printer to finish the order.

The Creality Hi answers the request when its macro has ended: ~9 s after a pause, 45 to 65 s after a resume. With a
10 s limit PrintWatch cut the request off ("ReadTimeout"), the web showed a 502 and the event log said ok:false,
although the printer had done what it was told (2026-10-09, twice). Against the simulated printer, which can hold the
answer back after changing state.

A pause first reads the printer's state to know it answers: an unreachable printer is a 502 at once, by that read and
not by how long a wait happens to take on the machine running the tests."""

import asyncio

import httpx

from app.api.v1 import printers as printers_api
from app.integrations.moonraker import client, command_log, print_guard
from tests.test_resume_guard import _scenario, _state


def _orders(base_url: str, action: str):
    return [c for c in command_log._commands if c.base_url == base_url and c.action == action]


def test_a_pause_with_a_slow_printer_is_accepted_without_waiting_for_its_answer(with_db, mock_server, mock_moonraker, monkeypatch):
    mock_moonraker.pause_seconds = 3.0  # the printer pauses at once and answers 3 s later
    monkeypatch.setattr(printers_api, "ACCEPT_WAIT_SECONDS", 0.3)

    async def steps(client_, printer_id, mock):
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        response = await client_.post(f"/api/v1/printers/{printer_id}/pause")
        right_after = [c.ok for c in _orders(mock_server, "pause")]  # the printer has not answered yet
        paused = await _state(mock)
        await asyncio.sleep(3.3)  # the printer's answer arrives
        return response, right_after, paused, [c.ok for c in _orders(mock_server, "pause")]

    response, right_after, paused, later = with_db(_scenario(mock_server, steps))
    assert response.status_code == 202
    assert response.json()["accepted"] is True and response.json()["pending"] is True and response.json()["action"] == "pause"
    assert right_after == [None]  # answered "accepted" while the order was still in the printer's hands, not failed
    assert paused == "paused"
    assert later == [True]


def test_a_pause_whose_state_read_fails_is_a_502_at_once_and_nothing_is_sent(with_db, mock_server, monkeypatch):
    """The printer is there (the simulated one is printing) but the state read fails: nothing may reach it."""
    monkeypatch.setattr(printers_api, "ACCEPT_WAIT_SECONDS", 0.0)  # a 502 here cannot come from waiting for the order

    async def unanswered(base_url):
        raise httpx.ConnectTimeout("")

    monkeypatch.setattr(print_guard, "read_print_state", unanswered)

    async def steps(client_, printer_id, mock):
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        response = await client_.post(f"/api/v1/printers/{printer_id}/pause")
        return response, await _state(mock)

    response, state = with_db(_scenario(mock_server, steps))
    assert response.status_code == 502 and "pause" in response.json()["detail"]
    assert state == "printing"  # the pause never reached the printer
    orders = _orders(mock_server, "pause")
    assert [o.ok for o in orders] == [False]  # noted for the event log, as a failure
    assert "no se envió" in orders[0].error and "ConnectTimeout" in orders[0].error


def test_a_pause_to_an_unreachable_printer_is_refused_and_noted(with_db, monkeypatch):
    monkeypatch.setattr(printers_api, "ACCEPT_WAIT_SECONDS", 0.0)  # whatever the machine's speed, the answer is the read's

    async def steps(client_, printer_id, mock):
        return await client_.post(f"/api/v1/printers/{printer_id}/pause")

    async def scenario(session_factory):
        return await _scenario("http://127.0.0.1:9", steps)(session_factory)

    response = with_db(scenario)
    assert response.status_code == 502
    assert [o.ok for o in _orders("http://127.0.0.1:9", "pause")] == [False]


def test_a_quick_refusal_of_the_order_itself_still_reaches_the_user_as_an_error(with_db, mock_server):
    async def steps(client_, printer_id, mock):
        return await client_.post(f"/api/v1/printers/{printer_id}/pause")  # standby: Moonraker answers 400

    response = with_db(_scenario(mock_server, steps))
    assert response.status_code == 502
    assert "pause" in response.json()["detail"]
    assert [c.ok for c in _orders(mock_server, "pause")] == [False]


def test_the_wait_for_the_printers_answer_outlasts_a_real_resume():
    assert client._ANSWER_TIMEOUT_SECONDS >= 90  # a real resume answered after 45 to 65 s
    assert client._CONNECT_TIMEOUT_SECONDS <= 10  # but an unreachable printer is still reported quickly
