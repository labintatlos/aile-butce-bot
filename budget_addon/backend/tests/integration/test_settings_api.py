"""Ayar uçlarının HTTP davranışı.

Servis katmanı ayrıca test edilir; buradaki amaç hata türlerinin doğru HTTP
koduna çevrildiğini doğrulamaktır. Kullanımda olan bir kaydı silme denemesi
`409` dönmelidir: istemci bunu "silinemez, pasife al" olarak yorumlar.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

HEADERS = {"X-Remote-User-Id": "70bbe879b6f145d9ba41e2ae8e2b81aa"}


async def test_card_can_be_created_and_renamed(client, seeded_users):
    created = await client.post(
        "/api/payment-methods",
        headers=HEADERS,
        json={"name": "Yeni Kart", "type": "credit_card", "statement_day": 26, "due_day": 10},
    )
    assert created.status_code == 201
    card_id = created.json()["id"]

    renamed = await client.patch(
        f"/api/payment-methods/{card_id}", headers=HEADERS, json={"name": "Adı Değişti"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Adı Değişti"


async def test_unused_card_is_deleted(client, seeded_users):
    created = await client.post(
        "/api/payment-methods",
        headers=HEADERS,
        json={"name": "Geçici Kart", "type": "credit_card", "statement_day": 1, "due_day": 15},
    )
    card_id = created.json()["id"]

    deleted = await client.delete(f"/api/payment-methods/{card_id}", headers=HEADERS)
    assert deleted.status_code == 204

    listing = await client.get("/api/payment-methods", headers=HEADERS)
    assert card_id not in {m["id"] for m in listing.json()}


async def test_card_in_use_returns_conflict(client, seeded_users, seeded_reference_data):
    await client.post(
        "/api/expenses",
        headers=HEADERS,
        json={
            "payment_method_id": seeded_reference_data["card_id"],
            "category_id": seeded_reference_data["category_id"],
            "transaction_date": "2026-09-08",
            "amount": "500",
        },
    )

    response = await client.delete(
        f"/api/payment-methods/{seeded_reference_data['card_id']}", headers=HEADERS
    )
    assert response.status_code == 409
    assert "pasife" in response.json()["detail"]


async def test_card_in_use_can_be_deactivated_over_http(
    client, seeded_users, seeded_reference_data
):
    response = await client.patch(
        f"/api/payment-methods/{seeded_reference_data['card_id']}",
        headers=HEADERS,
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_invalid_card_days_are_rejected(client, seeded_users):
    response = await client.post(
        "/api/payment-methods",
        headers=HEADERS,
        json={"name": "Bozuk", "type": "credit_card", "statement_day": 40, "due_day": 10},
    )
    assert response.status_code == 422


async def test_category_lifecycle_over_http(client, seeded_users):
    created = await client.post(
        "/api/categories", headers=HEADERS, json={"name": "Sinema", "emoji": "🎬"}
    )
    assert created.status_code == 201
    category_id = created.json()["id"]

    renamed = await client.patch(
        f"/api/categories/{category_id}", headers=HEADERS, json={"name": "Sinema & Tiyatro"}
    )
    assert renamed.json()["name"] == "Sinema & Tiyatro"

    deleted = await client.delete(f"/api/categories/{category_id}", headers=HEADERS)
    assert deleted.status_code == 204


async def test_category_in_use_returns_conflict(
    client, seeded_users, seeded_reference_data
):
    await client.post(
        "/api/expenses",
        headers=HEADERS,
        json={
            "payment_method_id": seeded_reference_data["cash_id"],
            "category_id": seeded_reference_data["category_id"],
            "transaction_date": "2026-09-08",
            "amount": "100",
        },
    )

    response = await client.delete(
        f"/api/categories/{seeded_reference_data['category_id']}", headers=HEADERS
    )
    assert response.status_code == 409


async def test_settings_endpoints_require_authentication(client):
    assert (await client.get("/api/payment-methods")).status_code == 401
    assert (await client.delete("/api/categories/1")).status_code == 401
