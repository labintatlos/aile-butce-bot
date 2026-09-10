"""Yetkilendirme testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-S*).

Bu testler gerçek HTTP istekleri üzerinden çalışır: bağımlılık zinciri,
başlık okuma ve hata kodları dahil tüm yol sınanır. Şifreyle girişin
ayrıntıları `test_web_login.py` içindedir.
"""

from __future__ import annotations

import pytest

from app.security.passwords import hash_password

pytestmark = pytest.mark.asyncio

AYKUT_HA_ID = "70bbe879b6f145d9ba41e2ae8e2b81aa"
KIOSK_HA_ID = "bbb2e9efbf9441f8aa5173d3164495ff"
PASSWORD = "gizli-sifre-1"


# ---------------------------------------------------------------------------
# Kimlik dogrulama yoklugu
# ---------------------------------------------------------------------------


async def test_i_s3_request_without_any_credential_is_unauthorized(client):
    response = await client.get("/api/bootstrap")
    assert response.status_code == 401


async def test_i_s4_the_old_telegram_header_opens_nothing(client, seeded_users):
    """Mini App kaldırıldı; `tma` başlığı artık hiçbir kimlik vermez."""
    response = await client.get(
        "/api/bootstrap",
        headers={"Authorization": "tma user=%7B%22id%22%3A111%7D&hash=abc123"},
    )
    assert response.status_code == 401
    assert "hash=" not in response.text


# ---------------------------------------------------------------------------
# Home Assistant Ingress
# ---------------------------------------------------------------------------


async def test_i_s10_mapped_home_assistant_user_is_accepted(client, seeded_users):
    response = await client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": AYKUT_HA_ID}
    )
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Aykut"


async def test_i_s11_unmapped_home_assistant_user_is_forbidden(client, seeded_users):
    """Paylaşılan kiosk hesabı eşlenmez: harcamayı kimin girdiği belirsizdir."""
    response = await client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": KIOSK_HA_ID}
    )
    assert response.status_code == 403


async def test_i_s7_deactivated_user_is_forbidden(client, seeded_users, async_session):
    seeded_users["aykut"].is_active = False
    await async_session.commit()

    response = await client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": AYKUT_HA_ID}
    )
    assert response.status_code == 403


async def test_a_pre_2_0_mapping_to_a_telegram_id_keeps_working(
    client_with, seeded_users, async_session
):
    """Güncellenen kurulumda `ha_user_map` değiştirilmeden panel açılmalıdır."""
    seeded_users["aykut"].telegram_user_id = 111
    seeded_users["aykut"].ha_user_id = None
    await async_session.commit()

    client = client_with(ha_user_map=f"{AYKUT_HA_ID}:111")
    response = await client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": AYKUT_HA_ID}
    )
    assert response.json()["user"]["display_name"] == "Aykut"


async def test_a_stored_home_assistant_id_works_without_a_mapping(
    client_with, seeded_users
):
    client = client_with(ha_user_map="")
    response = await client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": AYKUT_HA_ID}
    )
    assert response.status_code == 200


async def test_i_s12_ingress_header_is_ignored_when_not_trusted(
    public_client, seeded_users
):
    """İnternete açık örnek başlığa güvenmez.

    Aksi halde adresi bilen herkes başlığı uydurup istediği kullanıcı gibi
    davranabilirdi.
    """
    response = await public_client.get(
        "/api/bootstrap", headers={"X-Remote-User-Id": AYKUT_HA_ID}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Sahiplik
# ---------------------------------------------------------------------------


async def test_i_s8_client_cannot_choose_who_the_expense_belongs_to(
    client, seeded_users, seeded_reference_data
):
    """Gövdeye `created_by_user_id` koymak kaydın sahibini değiştirmez."""
    response = await client.post(
        "/api/expenses",
        headers={"X-Remote-User-Id": AYKUT_HA_ID},
        json={
            "payment_method_id": seeded_reference_data["cash_id"],
            "category_id": seeded_reference_data["category_id"],
            "transaction_date": "2026-09-08",
            "amount": "500",
            "created_by_user_id": seeded_users["aslihan"].id,
        },
    )
    assert response.status_code == 201
    assert response.json()["created_by"] == "Aykut"


async def test_i_s14_site_and_panel_write_to_the_same_user(
    client, client_with, seeded_users, seeded_reference_data, async_session
):
    seeded_users["aykut"].password_hash = hash_password(PASSWORD)
    await async_session.commit()
    payload = {
        "payment_method_id": seeded_reference_data["cash_id"],
        "category_id": seeded_reference_data["category_id"],
        "transaction_date": "2026-09-08",
        "amount": "100",
    }

    site = client_with(trust_ingress_headers=False, session_secret="test-anahtar")
    login = await site.post(
        "/api/auth/login", json={"username": "aykut", "password": PASSWORD}
    )
    assert login.status_code == 200
    by_site = await site.post("/api/expenses", json=payload)
    by_panel = await client.post(
        "/api/expenses", headers={"X-Remote-User-Id": AYKUT_HA_ID}, json=payload
    )

    assert by_site.json()["created_by"] == by_panel.json()["created_by"] == "Aykut"


async def test_health_endpoint_needs_no_credentials(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_api_documentation_is_closed_in_production(client):
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404
