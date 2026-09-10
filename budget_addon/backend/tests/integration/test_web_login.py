"""Web sitesi girişi: kullanıcı adı, şifre ve oturum çerezi.

Genel (internete açık) örnek üzerinden çalışır: Ingress başlığına güvenilmez,
kimlik yalnızca giriş çereziyle gelir.
"""

from __future__ import annotations

import pytest_asyncio

from app.auth_api import MAX_FAILED_LOGINS
from app.config import Settings
from app.models import User
from app.security import sessions
from app.security.passwords import hash_password, verify_password
from tests.conftest import _build_client, _test_settings

PASSWORD = "dogru-sifre-1"
OTHER_PASSWORD = "baska-sifre-2"


def _web_settings(**overrides) -> Settings:
    values = dict(trust_ingress_headers=False, session_secret="test-oturum-anahtari")
    values.update(overrides)
    return _test_settings(**values)


@pytest_asyncio.fixture()
async def web_client(async_engine, async_session, seeded_users):
    for key, username, password in (
        ("aykut", "aykut", PASSWORD),
        ("aslihan", "aslihan", OTHER_PASSWORD),
    ):
        seeded_users[key].username = username
        seeded_users[key].password_hash = hash_password(password)
    await async_session.commit()
    async with _build_client(async_engine, _web_settings()) as client:
        yield client


async def _login(client, username="aykut", password=PASSWORD, **extra):
    return await client.post(
        "/api/auth/login",
        json={"username": username, "password": password, **extra},
    )


def _with_cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"{sessions.COOKIE_NAME}={token}"}


# ---------------------------------------------------------------------------
# Giris ve cikis
# ---------------------------------------------------------------------------


async def test_login_sets_a_cookie_that_opens_the_api(web_client):
    response = await _login(web_client)

    assert response.status_code == 200
    assert response.json()["display_name"] == "Aykut"
    assert response.json()["auth_source"] == "session"
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie

    bootstrap = await web_client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["user"]["display_name"] == "Aykut"


async def test_username_is_not_case_sensitive(web_client):
    assert (await _login(web_client, username="  AYKUT ")).status_code == 200


async def test_wrong_password_and_unknown_user_get_the_same_answer(web_client):
    wrong = await _login(web_client, password="yanlis-sifre")
    unknown = await _login(web_client, username="kimse")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "set-cookie" not in wrong.headers


async def test_the_api_is_closed_without_a_cookie(web_client):
    assert (await web_client.get("/api/bootstrap")).status_code == 401


async def test_the_ingress_header_is_not_trusted_on_the_public_instance(web_client):
    response = await web_client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": "70bbe879b6f145d9ba41e2ae8e2b81aa"}
    )
    assert response.status_code == 401


async def test_a_tampered_cookie_is_rejected(web_client):
    token = (await _login(web_client)).cookies[sessions.COOKIE_NAME]
    web_client.cookies.clear()

    user_id, rest = token.split(".", 1)
    forged = f"{int(user_id) + 1}.{rest}"

    assert (await web_client.get("/api/bootstrap", headers=_with_cookie(token))).status_code == 200
    assert (await web_client.get("/api/bootstrap", headers=_with_cookie(forged))).status_code == 401


async def test_logout_ends_the_session(web_client):
    await _login(web_client)
    assert (await web_client.post("/api/auth/logout")).status_code == 204
    assert (await web_client.get("/api/bootstrap")).status_code == 401


async def test_short_session_cookie_is_not_persistent(web_client):
    response = await _login(web_client, remember=False)
    assert "max-age" not in response.headers["set-cookie"].lower()


# ---------------------------------------------------------------------------
# Veritabanindaki degisiklikler acik oturumlara yansir
# ---------------------------------------------------------------------------


async def test_changing_the_password_closes_open_sessions(
    web_client, async_session, seeded_users
):
    token = (await _login(web_client)).cookies[sessions.COOKIE_NAME]
    web_client.cookies.clear()

    aykut = await async_session.get(User, seeded_users["aykut"].id)
    aykut.password_hash = hash_password("yeni-sifre-3")
    await async_session.commit()

    assert (await web_client.get("/api/bootstrap", headers=_with_cookie(token))).status_code == 401
    assert (await _login(web_client)).status_code == 401
    assert (await _login(web_client, password="yeni-sifre-3")).status_code == 200


async def test_a_disabled_person_loses_access(web_client, async_session, seeded_users):
    token = (await _login(web_client)).cookies[sessions.COOKIE_NAME]
    web_client.cookies.clear()

    aykut = await async_session.get(User, seeded_users["aykut"].id)
    aykut.is_active = False
    await async_session.commit()

    assert (await web_client.get("/api/bootstrap", headers=_with_cookie(token))).status_code == 401
    assert (await _login(web_client)).status_code == 401
    assert (await _login(web_client, username="aslihan", password=OTHER_PASSWORD)).status_code == 200


# ---------------------------------------------------------------------------
# Kaba kuvvet korumasi
# ---------------------------------------------------------------------------


async def test_repeated_failures_are_throttled(web_client):
    for _ in range(MAX_FAILED_LOGINS):
        assert (await _login(web_client, password="yanlis-sifre")).status_code == 401

    blocked = await _login(web_client)
    assert blocked.status_code == 429


async def test_a_successful_login_resets_the_failure_count(web_client):
    for _ in range(MAX_FAILED_LOGINS - 1):
        await _login(web_client, password="yanlis-sifre")
    assert (await _login(web_client)).status_code == 200
    assert (await _login(web_client, password="yanlis-sifre")).status_code == 401
    assert (await _login(web_client)).status_code == 200


# ---------------------------------------------------------------------------
# Oturum sahibinin ayarlari
# ---------------------------------------------------------------------------


async def test_me_toggles_reminders(web_client):
    await _login(web_client)
    assert (await web_client.get("/api/me")).json()["reminders_enabled"] is True

    changed = await web_client.patch("/api/me", json={"reminders_enabled": False})
    assert changed.status_code == 200
    assert (await web_client.get("/api/me")).json()["reminders_enabled"] is False


async def test_users_lists_both_people(web_client):
    await _login(web_client)
    names = [user["display_name"] for user in (await web_client.get("/api/users")).json()]
    assert names == ["Aykut", "Aslıhan"]


async def test_ingress_instance_reports_its_source(client, seeded_users):
    response = await client.get(
        "/api/me", headers={"X-Remote-User-Id": "70bbe879b6f145d9ba41e2ae8e2b81aa"}
    )
    assert response.status_code == 200
    assert response.json()["auth_source"] == "ingress"


# ---------------------------------------------------------------------------
# Yapi taslari
# ---------------------------------------------------------------------------


def test_password_hash_round_trip():
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    assert verify_password(PASSWORD, stored)
    assert not verify_password("yanlis", stored)
    assert not verify_password(PASSWORD, None)
    assert not verify_password(PASSWORD, "bozuk$ozet")


def test_token_expires_and_needs_the_right_secret():
    token = sessions.issue_token(
        "anahtar", user_id=7, password_hash="ozet", lifetime_seconds=60, now=1_000
    )
    assert sessions.read_token("anahtar", token, now=1_030).user_id == 7
    assert sessions.read_token("anahtar", token, now=1_061) is None
    assert sessions.read_token("baska-anahtar", token, now=1_030) is None
    assert sessions.read_token("anahtar", "cop", now=1_030) is None


def test_generated_secret_is_shared_across_processes(tmp_path):
    settings = Settings(database_path=str(tmp_path / "budget.db"), _env_file=None)
    sessions._secret_cache.clear()
    first = sessions.resolve_secret(settings)
    sessions._secret_cache.clear()  # ikinci surec gibi davran

    assert len(first) == 64
    assert sessions.resolve_secret(settings) == first
    sessions._secret_cache.clear()
