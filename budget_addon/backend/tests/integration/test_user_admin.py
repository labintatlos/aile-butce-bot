"""Kişi yönetimi ve ilk yönetici kurulumu.

Kişiler eklenti ayarlarından değil sitedeki yönetici ekranından yönetilir. İlk
yönetici, eklenti günlüğüne yazılan kurulum koduyla oluşturulur.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import User
from app.security import sessions
from app.security.passwords import hash_password
from app.security.setup import SETUP_CODE_FILE_NAME
from tests.conftest import _build_client, _test_settings

PASSWORD = "yonetici-sifre-1"
MEMBER_PASSWORD = "uye-sifre-2"
SETUP_CODE = "1234-5678"


@pytest.fixture()
def settings(tmp_path):
    return _test_settings(
        trust_ingress_headers=False,
        session_secret="test-oturum-anahtari",
        database_path=str(tmp_path / "budget.db"),
    )


@pytest.fixture()
def code_file(settings, tmp_path):
    path = tmp_path / SETUP_CODE_FILE_NAME
    path.write_text(SETUP_CODE, encoding="ascii")
    return path


@pytest_asyncio.fixture()
async def site(async_engine, settings):
    async with _build_client(async_engine, settings) as client:
        yield client


@pytest_asyncio.fixture()
async def family(async_session, seeded_users):
    """Aykut yönetici, Aslıhan üye; ikisinin de girişi var."""
    aykut, aslihan = seeded_users["aykut"], seeded_users["aslihan"]
    aykut.username, aykut.password_hash, aykut.is_admin = "aykut", hash_password(PASSWORD), True
    aslihan.username, aslihan.password_hash = "aslihan", hash_password(MEMBER_PASSWORD)
    await async_session.commit()
    return seeded_users


async def _login(client, username, password):
    return await client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"{sessions.COOKIE_NAME}={token}"}


# ---------------------------------------------------------------------------
# Ilk kurulum
# ---------------------------------------------------------------------------


async def test_a_fresh_install_asks_for_setup_and_writes_a_code(site, tmp_path):
    response = await site.get("/api/setup")

    assert response.json() == {"required": True}
    assert (tmp_path / SETUP_CODE_FILE_NAME).read_text(encoding="ascii").count("-") == 1


async def test_setup_refuses_a_wrong_code(site, code_file, seeded_users):
    response = await site.post("/api/setup/verify", json={"code": "1111-1111"})
    assert response.status_code == 400

    created = await site.post(
        "/api/setup",
        json={"code": "0000", "display_name": "Saldırgan", "username": "kotu", "password": "kotu-sifre-1"},
    )
    assert created.status_code == 400


async def test_setup_claims_an_existing_person(site, code_file, seeded_users, async_session):
    people = await site.post("/api/setup/verify", json={"code": "12345678"})
    assert [person["display_name"] for person in people.json()] == ["Aykut", "Aslıhan"]

    response = await site.post(
        "/api/setup",
        json={
            "code": SETUP_CODE,
            "user_id": seeded_users["aykut"].id,
            "username": "Aykut",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["is_admin"] is True
    assert response.json()["username"] == "aykut"
    assert (await site.get("/api/bootstrap")).status_code == 200
    assert not code_file.exists()
    assert (await site.get("/api/setup")).json() == {"required": False}

    again = await site.post(
        "/api/setup",
        json={"code": SETUP_CODE, "display_name": "İkinci", "username": "ikinci", "password": PASSWORD},
    )
    assert again.status_code == 409
    assert await async_session.scalar(select(User).where(User.username == "ikinci")) is None


async def test_setup_can_create_a_new_person(site, code_file):
    response = await site.post(
        "/api/setup",
        json={"code": SETUP_CODE, "display_name": "  Ayşe  ", "username": "ayse", "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Ayşe"


async def test_setup_validates_the_new_login(site, code_file):
    short = await site.post(
        "/api/setup",
        json={"code": SETUP_CODE, "display_name": "Ayşe", "username": "ayse", "password": "kisa"},
    )
    turkish = await site.post(
        "/api/setup",
        json={"code": SETUP_CODE, "display_name": "Ayşe", "username": "ayşe", "password": PASSWORD},
    )

    assert short.status_code == 422 and "en az 8" in short.json()["detail"]
    assert turkish.status_code == 422


# ---------------------------------------------------------------------------
# Kisiler ekrani
# ---------------------------------------------------------------------------


async def test_an_admin_adds_a_person_who_can_then_log_in(site, family):
    await _login(site, "aykut", PASSWORD)
    created = await site.post(
        "/api/admin/users",
        json={"display_name": "Deniz", "username": "deniz", "password": "deniz-sifre-1"},
    )
    assert created.status_code == 201
    assert created.json()["has_login"] is True and created.json()["is_admin"] is False

    site.cookies.clear()
    login = await _login(site, "deniz", "deniz-sifre-1")
    assert login.status_code == 200
    assert login.json()["is_admin"] is False


async def test_members_cannot_manage_people(site, family):
    await _login(site, "aslihan", MEMBER_PASSWORD)

    assert (await site.get("/api/admin/users")).status_code == 403
    assert (
        await site.post(
            "/api/admin/users",
            json={"display_name": "X", "username": "xxx", "password": "xxxx-sifre-1"},
        )
    ).status_code == 403
    assert (
        await site.patch(f"/api/admin/users/{family['aslihan'].id}", json={"is_admin": True})
    ).status_code == 403


async def test_an_admin_resets_a_password_and_old_sessions_close(site, family):
    token = (await _login(site, "aslihan", MEMBER_PASSWORD)).cookies[sessions.COOKIE_NAME]
    site.cookies.clear()

    await _login(site, "aykut", PASSWORD)
    changed = await site.patch(
        f"/api/admin/users/{family['aslihan'].id}", json={"password": "yeni-sifre-9"}
    )
    assert changed.status_code == 200
    site.cookies.clear()

    assert (await site.get("/api/bootstrap", headers=_cookie(token))).status_code == 401
    assert (await _login(site, "aslihan", MEMBER_PASSWORD)).status_code == 401
    assert (await _login(site, "aslihan", "yeni-sifre-9")).status_code == 200


async def test_disabling_a_person_closes_their_access(site, family):
    token = (await _login(site, "aslihan", MEMBER_PASSWORD)).cookies[sessions.COOKIE_NAME]
    site.cookies.clear()

    await _login(site, "aykut", PASSWORD)
    disabled = await site.patch(
        f"/api/admin/users/{family['aslihan'].id}", json={"is_active": False}
    )
    assert disabled.json()["is_active"] is False
    site.cookies.clear()

    assert (await site.get("/api/bootstrap", headers=_cookie(token))).status_code == 401
    assert (await _login(site, "aslihan", MEMBER_PASSWORD)).status_code == 401


async def test_an_admin_cannot_lock_themselves_out(site, family):
    await _login(site, "aykut", PASSWORD)
    me = family["aykut"].id

    assert (await site.patch(f"/api/admin/users/{me}", json={"is_active": False})).status_code == 409
    assert (await site.patch(f"/api/admin/users/{me}", json={"is_admin": False})).status_code == 409
    assert (await site.get("/api/me")).json()["is_admin"] is True


async def test_an_admin_changing_their_own_password_stays_logged_in(site, family):
    await _login(site, "aykut", PASSWORD)

    changed = await site.patch(
        f"/api/admin/users/{family['aykut'].id}", json={"password": "yeni-yonetici-1"}
    )

    assert changed.status_code == 200
    assert (await site.get("/api/bootstrap")).status_code == 200


async def test_usernames_stay_unique_and_valid(site, family):
    await _login(site, "aykut", PASSWORD)

    duplicate = await site.post(
        "/api/admin/users",
        json={"display_name": "Kopya", "username": "ASLIHAN", "password": "kopya-sifre-1"},
    )
    renamed = await site.patch(
        f"/api/admin/users/{family['aslihan'].id}", json={"username": "aykut"}
    )

    assert duplicate.status_code == 422
    assert renamed.status_code == 422


async def test_a_person_without_a_login_gets_one_only_with_both_fields(
    site, family, async_session
):
    await _login(site, "aykut", PASSWORD)
    guest = User(display_name="Misafir", role="owner")
    async_session.add(guest)
    await async_session.commit()

    half = await site.patch(f"/api/admin/users/{guest.id}", json={"username": "misafir"})
    full = await site.patch(
        f"/api/admin/users/{guest.id}",
        json={"username": "misafir", "password": "misafir-sifre-1"},
    )

    assert half.status_code == 422
    assert full.status_code == 200 and full.json()["has_login"] is True


async def test_the_list_shows_everyone_including_disabled_people(site, family, async_session):
    family["aslihan"].is_active = False
    await async_session.commit()
    await _login(site, "aykut", PASSWORD)

    people = (await site.get("/api/admin/users")).json()

    assert [(p["display_name"], p["is_active"]) for p in people] == [
        ("Aykut", True),
        ("Aslıhan", False),
    ]


# ---------------------------------------------------------------------------
# Kisinin kendi sifresi
# ---------------------------------------------------------------------------


async def test_a_person_changes_their_own_password(site, family):
    await _login(site, "aslihan", MEMBER_PASSWORD)

    wrong = await site.post(
        "/api/me/password",
        json={"current_password": "yanlis-sifre", "new_password": "yeni-uye-sifre-3"},
    )
    right = await site.post(
        "/api/me/password",
        json={"current_password": MEMBER_PASSWORD, "new_password": "yeni-uye-sifre-3"},
    )

    assert wrong.status_code == 400
    assert right.status_code == 200
    assert (await site.get("/api/bootstrap")).status_code == 200

    site.cookies.clear()
    assert (await _login(site, "aslihan", MEMBER_PASSWORD)).status_code == 401
    assert (await _login(site, "aslihan", "yeni-uye-sifre-3")).status_code == 200
