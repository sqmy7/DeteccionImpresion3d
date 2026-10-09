"""The web keeps its session alive with POST /auth/refresh while it is open (a print lasts hours, the token one hour),
but the session still ends jwt_max_session_hours after the login that began it."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password
from app.db.models import User, UserRole
from app.db.session import get_db
from app.main import app


def _run(with_db, steps):
    async def scenario(session_factory):
        async with session_factory() as db:
            user = User(username=f"t-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local",
                        hashed_password=hash_password("secreto-de-prueba"), role=UserRole.admin)
            db.add(user)
            await db.commit()
            username, user_id = user.username, user.id

        async def test_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await steps(client, username, user_id)
        finally:
            app.dependency_overrides.clear()

    return with_db(scenario)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_refresh_gives_a_working_token_that_keeps_the_original_login_time(with_db):
    async def steps(client, username, user_id):
        login = await client.post("/api/v1/auth/login", data={"username": username, "password": "secreto-de-prueba"})
        first = login.json()["access_token"]
        refreshed = await client.post("/api/v1/auth/refresh", headers=_bearer(first))
        second = refreshed.json()["access_token"]
        me = await client.get("/api/v1/auth/me", headers=_bearer(second))
        return first, refreshed, second, me

    first, refreshed, second, me = _run(with_db, steps)
    assert refreshed.status_code == 200 and me.status_code == 200
    old, new = decode_access_token(first), decode_access_token(second)
    assert new["sub"] == old["sub"] and new["auth_time"] == old["auth_time"]
    assert new["exp"] >= old["exp"]


def test_the_session_ends_after_the_maximum_however_often_it_is_renewed(with_db):
    started = datetime.now(timezone.utc) - timedelta(hours=settings.jwt_max_session_hours, minutes=1)

    async def steps(client, username, user_id):
        too_old = create_access_token(str(user_id), auth_time=started)  # still inside its own hour
        return await client.post("/api/v1/auth/refresh", headers=_bearer(too_old))

    response = _run(with_db, steps)
    assert response.status_code == 401
    assert "log in again" in response.json()["detail"]


def test_renewing_again_and_again_does_not_move_the_start(with_db):
    started = datetime.now(timezone.utc) - timedelta(hours=3)

    async def steps(client, username, user_id):
        token = create_access_token(str(user_id), auth_time=started)
        for _ in range(3):
            response = await client.post("/api/v1/auth/refresh", headers=_bearer(token))
            token = response.json()["access_token"]
        return token

    token = _run(with_db, steps)
    assert decode_access_token(token)["auth_time"] == int(started.timestamp())


def test_a_token_from_before_auth_time_existed_is_renewed_and_starts_counting_now(with_db):
    async def steps(client, username, user_id):
        old_style = jwt.encode(
            {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        response = await client.post("/api/v1/auth/refresh", headers=_bearer(old_style))
        return response

    response = _run(with_db, steps)
    assert response.status_code == 200
    assert abs(decode_access_token(response.json()["access_token"])["auth_time"] - datetime.now(timezone.utc).timestamp()) < 10


def test_an_expired_or_missing_token_cannot_be_renewed(with_db):
    async def steps(client, username, user_id):
        expired = create_access_token(str(user_id), expires_delta=timedelta(seconds=-5))
        return (
            await client.post("/api/v1/auth/refresh", headers=_bearer(expired)),
            await client.post("/api/v1/auth/refresh"),
        )

    expired, missing = _run(with_db, steps)
    assert (expired.status_code, missing.status_code) == (401, 401)
