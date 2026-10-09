"""Cancelling from the web: administrators only, with the typed confirmation, one order at a time, not twice
in a row, and only if the printer itself says it is printing or paused. Against the simulated printer, which
really changes state. Nothing here reaches a real printer."""

import asyncio
import uuid

import httpx

from app.api.deps import get_current_user, require_admin
from app.db.models import IntegrationType, Printer, User, UserRole
from app.db.session import get_db
from app.integrations.moonraker import command_log, print_guard
from app.main import app

CONFIRM = {"confirmation": "CANCELAR"}


def _sent(base_url: str, action: str = "cancel") -> list:
    return [c for c in command_log._commands if c.base_url == base_url and c.action == action]


def _scenario(mock_server, steps, role: UserRole = UserRole.admin):
    """Runs steps(client, printer_id, mock) with the API served in-process against a printer record pointing
    at the simulated Moonraker."""

    async def scenario(session_factory):
        command_log._commands.clear()
        async with session_factory() as db:
            user = User(username=f"tester-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local", hashed_password="x", role=role)
            printer = Printer(name="Simulada", octoprint_url=mock_server, octoprint_api_key_encrypted="",
                              integration_type=IntegrationType.moonraker)
            db.add_all([user, printer])
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user  # require_admin stays the real one: it checks the role
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client, \
                    httpx.AsyncClient(base_url=mock_server) as mock:
                return await steps(client, printer.id, mock)
        finally:
            app.dependency_overrides.clear()

    return scenario


async def _state(mock) -> str:
    response = await mock.get("/printer/objects/query", params={"print_stats": "state"})
    return response.json()["result"]["status"]["print_stats"]["state"]


async def _start(mock) -> None:
    (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
    assert await _state(mock) == "printing"


def test_without_the_typed_confirmation_nothing_is_sent(with_db, mock_server):
    async def steps(client, printer_id, mock):
        await _start(mock)
        url = f"/api/v1/printers/{printer_id}/cancel"
        return [
            await client.post(url),  # no body
            await client.post(url, json={}),
            await client.post(url, json={"confirmation": "cancelar"}),  # the word must be exactly CANCELAR
            await client.post(url, json={"confirmation": "SI"}),
        ], await _state(mock)

    responses, state = with_db(_scenario(mock_server, steps))
    assert [r.status_code for r in responses] == [422, 422, 422, 422]
    assert state == "printing" and _sent(mock_server) == []


def test_a_viewer_cannot_cancel(with_db, mock_server):
    async def steps(client, printer_id, mock):
        await _start(mock)
        return await client.post(f"/api/v1/printers/{printer_id}/cancel", json=CONFIRM), await _state(mock)

    response, state = with_db(_scenario(mock_server, steps, role=UserRole.viewer))
    assert response.status_code == 403 and state == "printing" and _sent(mock_server) == []


def test_cancel_is_refused_unless_the_printer_is_printing_or_paused(with_db, mock_server):
    async def steps(client, printer_id, mock):
        url = f"/api/v1/printers/{printer_id}/cancel"
        idle = await client.post(url, json=CONFIRM)  # standby
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        (await mock.post("/mock/error")).raise_for_status()
        failed = await client.post(url, json=CONFIRM)
        return idle, failed

    idle, failed = with_db(_scenario(mock_server, steps))
    assert [idle.status_code, failed.status_code] == [409, 409]
    assert "standby" in idle.json()["detail"] and "error" in failed.json()["detail"]
    assert _sent(mock_server) == []  # nothing reached the printer


def test_cancel_goes_through_while_printing_and_while_paused_and_is_attributed_to_the_user(with_db, mock_server, monkeypatch):
    monkeypatch.setattr(print_guard, "CANCEL_COOLDOWN_SECONDS", 0.0)

    async def steps(client, printer_id, mock):
        url = f"/api/v1/printers/{printer_id}/cancel"
        await _start(mock)
        while_printing = await client.post(url, json=CONFIRM)
        state_after_printing = await _state(mock)
        await _start(mock)
        (await mock.post("/printer/print/pause")).raise_for_status()
        assert await _state(mock) == "paused"
        while_paused = await client.post(url, json=CONFIRM)
        return while_printing, state_after_printing, while_paused, await _state(mock)

    while_printing, state_after_printing, while_paused, state_after_paused = with_db(_scenario(mock_server, steps))
    assert (while_printing.status_code, while_paused.status_code) == (204, 204)
    assert (state_after_printing, state_after_paused) == ("cancelled", "cancelled")
    orders = _sent(mock_server)
    assert len(orders) == 2 and all(o.requested_by.startswith("tester-") and o.requested_by.endswith(" (web)") and o.ok for o in orders)


def test_two_simultaneous_clicks_send_one_order(with_db, mock_server, monkeypatch):
    # Both requests are inside the guard at the same moment (the state read is slowed down): without the lock both
    # would pass the cooldown check, because nothing has been recorded yet, and two orders would go out.
    real_read = print_guard.read_print_state

    async def slow_read(base_url: str):
        await asyncio.sleep(0.3)
        return await real_read(base_url)

    monkeypatch.setattr(print_guard, "read_print_state", slow_read)

    async def steps(client, printer_id, mock):
        await _start(mock)
        url = f"/api/v1/printers/{printer_id}/cancel"
        return await asyncio.gather(client.post(url, json=CONFIRM), client.post(url, json=CONFIRM)), await _state(mock)

    responses, state = with_db(_scenario(mock_server, steps))
    assert sorted(r.status_code for r in responses) == [204, 409]
    assert state == "cancelled" and len(_sent(mock_server)) == 1


def test_a_second_cancel_right_after_the_first_is_refused_even_if_printing_again(with_db, mock_server):
    async def steps(client, printer_id, mock):
        url = f"/api/v1/printers/{printer_id}/cancel"
        await _start(mock)
        first = await client.post(url, json=CONFIRM)
        await _start(mock)  # another print begins: a new cancel is not allowed yet
        second = await client.post(url, json=CONFIRM)
        return first, second, await _state(mock)

    first, second, state = with_db(_scenario(mock_server, steps))
    assert (first.status_code, second.status_code) == (204, 409)
    assert "hace" in second.json()["detail"] and state == "printing"
    assert len(_sent(mock_server)) == 1


def test_cancel_and_resume_share_one_lock_so_they_never_run_at_once(with_db, mock_server):
    async def steps(client, printer_id, mock):
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        (await mock.post("/printer/print/pause")).raise_for_status()
        return await asyncio.gather(
            client.post(f"/api/v1/printers/{printer_id}/cancel", json=CONFIRM),
            client.post(f"/api/v1/printers/{printer_id}/resume"),
        )

    cancel, resume = with_db(_scenario(mock_server, steps))
    assert sorted([cancel.status_code, resume.status_code]) == [204, 409]
    assert len(_sent(mock_server, "cancel")) + len(_sent(mock_server, "resume")) == 1


def test_cancel_after_the_cooldown_works_again(with_db, mock_server, monkeypatch):
    monkeypatch.setattr(print_guard, "CANCEL_COOLDOWN_SECONDS", 0.2)

    async def steps(client, printer_id, mock):
        url = f"/api/v1/printers/{printer_id}/cancel"
        await _start(mock)
        first = await client.post(url, json=CONFIRM)
        await _start(mock)
        await asyncio.sleep(0.3)
        return first, await client.post(url, json=CONFIRM)

    first, second = with_db(_scenario(mock_server, steps))
    assert (first.status_code, second.status_code) == (204, 204)
    assert len(_sent(mock_server)) == 2


def test_if_the_state_cannot_be_read_nothing_is_sent(with_db):
    async def steps(client, printer_id, mock):
        return await client.post(f"/api/v1/printers/{printer_id}/cancel", json=CONFIRM)

    # A printer address nobody listens on: the state read fails before any order is sent.
    response = with_db(_scenario("http://127.0.0.1:9", steps))
    assert response.status_code == 502
    assert _sent("http://127.0.0.1:9") == []
