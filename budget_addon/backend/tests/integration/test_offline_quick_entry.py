"""Çevrimdışı kuyruktan gelen hızlı girişler.

Telefon bağlantı yokken girilen harcamayı saklar ve bağlantı gelince gönderir.
Buradaki iki risk: yanıt kaybolup aynı kaydın iki kez yazılması ve kaydın
gönderildiği güne (girildiği gün yerine) düşmesi.
"""

from __future__ import annotations

from datetime import date, timedelta

from tests.integration.test_receipt_upload import site  # noqa: F401  (fixture)

REF = "0b7c2d1e-4f5a-4b6c-8d9e-0f1a2b3c4d5e"


async def _today(client) -> date:
    return date.fromisoformat((await client.get("/api/bootstrap")).json()["today"])


async def _total(client) -> int:
    return (await client.get("/api/expenses")).json()["total"]


async def test_an_offline_entry_keeps_the_day_it_was_entered(site):  # noqa: F811
    yesterday = await _today(site) - timedelta(days=1)

    expense = (
        await site.post(
            "/api/expenses/quick",
            json={"text": "40 market", "transaction_date": yesterday.isoformat()},
        )
    ).json()["expense"]

    assert expense["transaction_date"] == yesterday.isoformat()


async def test_sending_the_same_entry_twice_records_it_once(site):  # noqa: F811
    body = {"text": "60 market simit", "client_ref": REF}

    first = (await site.post("/api/expenses/quick", json=body)).json()["expense"]
    second = (await site.post("/api/expenses/quick", json=body)).json()["expense"]

    assert first["id"] == second["id"]
    assert await _total(site) == 1


async def test_a_resent_entry_does_not_revive_a_deleted_expense(site):  # noqa: F811
    body = {"text": "60 market", "client_ref": REF}
    first = (await site.post("/api/expenses/quick", json=body)).json()["expense"]
    assert (await site.delete(f"/api/expenses/{first['id']}")).status_code == 204

    again = (await site.post("/api/expenses/quick", json=body)).json()["expense"]

    assert again["id"] == first["id"]
    assert await _total(site) == 0


async def test_dates_in_the_future_or_long_past_are_refused(site):  # noqa: F811
    today = await _today(site)

    tomorrow = await site.post(
        "/api/expenses/quick",
        json={"text": "40 market", "transaction_date": (today + timedelta(days=1)).isoformat()},
    )
    ancient = await site.post(
        "/api/expenses/quick",
        json={"text": "40 market", "transaction_date": (today - timedelta(days=61)).isoformat()},
    )

    assert tomorrow.status_code == 422
    assert ancient.status_code == 422
    assert await _total(site) == 0


async def test_a_malformed_reference_is_refused(site):  # noqa: F811
    response = await site.post(
        "/api/expenses/quick", json={"text": "40 market", "client_ref": "kısa ref!"}
    )
    assert response.status_code == 422


async def test_an_ambiguous_offline_entry_waits_for_a_category(site):  # noqa: F811
    result = (
        await site.post("/api/expenses/quick", json={"text": "90 kahve", "client_ref": REF})
    ).json()

    assert result["expense"] is None
    assert result["amount_minor"] == 9_000
    assert await _total(site) == 0
