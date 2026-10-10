"""Resuming from the web: one order at a time, not twice in a row, and only if the printer says it is
paused. Against the simulated printer, which really changes state."""

import asyncio
import uuid

import httpx

from app.api.deps import get_current_user, require_admin
from app.db.models import IntegrationType, Printer, User, UserRole
from app.db.session import get_db
from app.integrations.moonraker import command_log, print_guard
from app.main import app


def _resumes_sent(base_url: str) -> int:
    return sum(1 for command in command_log._commands if command.base_url == base_url and command.action == "resume")


def _scenario(mock_server, steps):
    """Runs steps(client, printer_id, mock) with the API served in-process against a printer record
    pointing at the simulated Moonraker."""

    async def scenario(session_factory):
        command_log._commands.clear()
        async with session_factory() as db:
            user = User(username=f"t-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local",
                        hashed_password="x", role=UserRole.admin)
            printer = Printer(name="Simulada", octoprint_url=mock_server, octoprint_api_key_encrypted="",
                              integration_type=IntegrationType.moonraker)
            db.add_all([user, printer])
            await db.commit()

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_admin] = lambda: user
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


async def _start_and_pause(mock) -> None:
    (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
    (await mock.post("/printer/print/pause")).raise_for_status()
    assert await _state(mock) == "paused"


def test_resume_is_refused_unless_the_printer_is_paused(with_db, mock_server):
    async def steps(client, printer_id, mock):
        idle = await client.post(f"/api/v1/printers/{printer_id}/resume")  # standby
        (await mock.post("/printer/print/start", params={"filename": "mock_box.gcode"})).raise_for_status()
        printing = await client.post(f"/api/v1/printers/{printer_id}/resume")
        (await mock.post("/mock/error")).raise_for_status()
        failed = await client.post(f"/api/v1/printers/{printer_id}/resume")
        return idle, printing, failed

    idle, printing, failed = with_db(_scenario(mock_server, steps))
    assert [idle.status_code, printing.status_code, failed.status_code] == [409, 409, 409]
    assert "standby" in idle.json()["detail"] and "printing" in printing.json()["detail"] and "error" in failed.json()["detail"]
    assert _resumes_sent(mock_server) == 0  # nothing reached the printer


def test_resume_goes_through_when_paused_and_two_simultaneous_clicks_send_one_order(with_db, mock_server):
    async def steps(client, printer_id, mock):
        await _start_and_pause(mock)
        responses = await asyncio.gather(
            client.post(f"/api/v1/printers/{printer_id}/resume"), client.post(f"/api/v1/printers/{printer_id}/resume")
        )
        return responses, await _state(mock)

    responses, state = with_db(_scenario(mock_server, steps))
    assert sorted(response.status_code for response in responses) == [202, 409]
    assert state == "printing"
    assert _resumes_sent(mock_server) == 1


def test_a_second_resume_right_after_the_first_is_refused_even_if_paused_again(with_db, mock_server):
    async def steps(client, printer_id, mock):
        await _start_and_pause(mock)
        first = await client.post(f"/api/v1/printers/{printer_id}/resume")
        (await mock.post("/printer/print/pause")).raise_for_status()
        second = await client.post(f"/api/v1/printers/{printer_id}/resume")
        return first, second

    first, second = with_db(_scenario(mock_server, steps))
    assert first.status_code == 202 and second.status_code == 409
    assert "hace" in second.json()["detail"]
    assert _resumes_sent(mock_server) == 1


def test_resume_after_the_cooldown_works_again(with_db, mock_server, monkeypatch):
    monkeypatch.setattr(print_guard, "RESUME_COOLDOWN_SECONDS", 0.2)

    async def steps(client, printer_id, mock):
        await _start_and_pause(mock)
        first = await client.post(f"/api/v1/printers/{printer_id}/resume")
        (await mock.post("/printer/print/pause")).raise_for_status()
        await asyncio.sleep(0.3)
        return first, await client.post(f"/api/v1/printers/{printer_id}/resume")

    first, second = with_db(_scenario(mock_server, steps))
    assert (first.status_code, second.status_code) == (202, 202)
    assert _resumes_sent(mock_server) == 2


def test_if_the_state_cannot_be_read_nothing_is_sent(with_db):
    async def steps(client, printer_id, mock):
        return await client.post(f"/api/v1/printers/{printer_id}/resume")

    async def scenario(session_factory):
        # A printer address nobody listens on: the state read fails before any order is sent.
        return await _scenario("http://127.0.0.1:9", lambda c, p, m: steps(c, p, m))(session_factory)

    # _scenario opens a client on the mock address; an unreachable one is fine as it is never used.
    response = with_db(scenario)
    assert response.status_code == 502
    assert _resumes_sent("http://127.0.0.1:9") == 0
