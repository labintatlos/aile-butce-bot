"""Yetkilendirme testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-S*).

Bu testler gerçek HTTP istekleri üzerinden çalışır: bağımlılık zinciri,
başlık okuma ve hata kodları dahil tüm yol sınanır.
"""

from __future__ import annotations

import time

import pytest

from app.security.telegram_auth import build_init_data

pytestmark = pytest.mark.asyncio

BOT_TOKEN = "123456:TEST-TOKEN-ONLY"
AYKUT_TELEGRAM_ID = 111
AYKUT_HA_ID = "70bbe879b6f145d9ba41e2ae8e2b81aa"
KIOSK_HA_ID = "bbb2e9efbf9441f8aa5173d3164495ff"


def telegram_header(user_id: int = AYKUT_TELEGRAM_ID, age_seconds: int = 0) -> dict:
    init_data = build_init_data(
        BOT_TOKEN,
        {"id": user_id, "first_name": "Aykut"},
        auth_date=int(time.time()) - age_seconds,
    )
    return {"Authorization": f"tma {init_data}"}


# ---------------------------------------------------------------------------
# Kimlik dogrulama yoklugu ve bozuk imzalar
# ---------------------------------------------------------------------------


async def test_i_s3_request_without_any_credential_is_unauthorized(client):
    response = await client.get("/api/bootstrap")
    assert response.status_code == 401


async def test_i_s4_tampered_signature_is_rejected(client):
    headers = telegram_header()
    headers["Authorization"] = headers["Authorization"][:-4] + "0000"
    response = await client.get("/api/bootstrap", headers=headers)
    assert response.status_code == 401


async def test_i_s5_expired_session_is_rejected(client):
    response = await client.get(
        "/api/bootstrap", headers=telegram_header(age_seconds=90_000)
    )
    assert response.status_code == 401


async def test_valid_telegram_signature_is_accepted(client, seeded_users):
    response = await client.get("/api/bootstrap", headers=telegram_header())
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Aykut"


async def test_i_s6_valid_signature_from_an_unauthorized_person_is_forbidden(
    client, seeded_users
):
    response = await client.get("/api/bootstrap", headers=telegram_header(user_id=999))
    assert response.status_code == 403


async def test_i_s7_deactivated_user_is_forbidden(client, seeded_users, async_session):
    seeded_users["aykut"].is_active = False
    await async_session.commit()

    response = await client.get("/api/bootstrap", headers=telegram_header())
    assert response.status_code == 403


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

    # Ayni ornek gecerli Telegram imzasini kabul etmeye devam eder.
    accepted = await public_client.get("/api/bootstrap", headers=telegram_header())
    assert accepted.status_code == 200


# ---------------------------------------------------------------------------
# Gelistirme basligi
# ---------------------------------------------------------------------------


async def test_i_s13_dev_header_is_ignored_in_production(client, seeded_users):
    response = await client.get(
        "/api/bootstrap", headers={"X-Dev-Telegram-User-Id": str(AYKUT_TELEGRAM_ID)}
    )
    assert response.status_code == 401


async def test_dev_header_works_when_explicitly_enabled(dev_client, seeded_users):
    response = await dev_client.get(
        "/api/bootstrap", headers={"X-Dev-Telegram-User-Id": str(AYKUT_TELEGRAM_ID)}
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Sahiplik ve sizinti
# ---------------------------------------------------------------------------


async def test_i_s8_client_cannot_choose_who_the_expense_belongs_to(
    client, seeded_users, seeded_reference_data
):
    """Gövdeye `created_by_user_id` koymak kaydın sahibini değiştirmez."""
    response = await client.post(
        "/api/expenses",
        headers=telegram_header(),
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


async def test_i_s14_both_entry_points_write_to_the_same_user(
    client, seeded_users, seeded_reference_data
):
    payload = {
        "payment_method_id": seeded_reference_data["cash_id"],
        "category_id": seeded_reference_data["category_id"],
        "transaction_date": "2026-09-08",
        "amount": "100",
    }
    by_telegram = await client.post(
        "/api/expenses", headers=telegram_header(), json=payload
    )
    by_ingress = await client.post(
        "/api/expenses", headers={"X-Remote-User-Id": AYKUT_HA_ID}, json=payload
    )

    assert by_telegram.json()["created_by"] == by_ingress.json()["created_by"] == "Aykut"


async def test_i_s9_error_responses_never_leak_the_token_or_init_data(client):
    response = await client.get("/api/bootstrap", headers=telegram_header(user_id=999))
    body = response.text
    assert BOT_TOKEN not in body
    assert "hash=" not in body


async def test_health_endpoint_needs_no_credentials(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_api_documentation_is_closed_in_production(client):
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404
