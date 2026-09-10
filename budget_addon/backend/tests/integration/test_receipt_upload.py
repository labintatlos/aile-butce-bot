"""Sitede fiş fotoğrafı ve hızlı giriş (önceden yalnızca Telegram'daydı)."""

from __future__ import annotations

import pytest_asyncio

from app.security.passwords import hash_password
from tests.conftest import _build_client, _test_settings

PASSWORD = "fis-sifre-1"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200


@pytest_asyncio.fixture()
async def site(async_engine, async_session, tmp_path, seeded_users, seeded_reference_data):
    seeded_users["aykut"].username = "aykut"
    seeded_users["aykut"].password_hash = hash_password(PASSWORD)
    await async_session.commit()
    settings = _test_settings(
        trust_ingress_headers=False,
        session_secret="test-oturum-anahtari",
        database_path=str(tmp_path / "budget.db"),
    )
    async with _build_client(async_engine, settings) as client:
        response = await client.post(
            "/api/auth/login", json={"username": "aykut", "password": PASSWORD}
        )
        assert response.status_code == 200
        yield client


async def _new_expense(site, reference) -> int:
    bootstrap = (await site.get("/api/bootstrap")).json()
    response = await site.post(
        "/api/expenses",
        json={
            "payment_method_id": reference["cash_id"],
            "category_id": reference["category_id"],
            "transaction_date": bootstrap["today"],
            "amount": "120",
            "installment_count": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _stored(tmp_path) -> list[str]:
    directory = tmp_path / "receipts"
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


# ---------------------------------------------------------------------------
# Fis fotografi
# ---------------------------------------------------------------------------


async def test_a_receipt_photo_is_stored_and_shown(site, seeded_reference_data, tmp_path):
    expense_id = await _new_expense(site, seeded_reference_data)

    uploaded = await site.put(
        f"/api/expenses/{expense_id}/receipt", content=JPEG, headers={"Content-Type": "image/jpeg"}
    )

    assert uploaded.status_code == 204
    assert (await site.get(f"/api/expenses/{expense_id}")).json()["has_receipt"] is True
    shown = await site.get(f"/api/expenses/{expense_id}/receipt")
    assert shown.status_code == 200
    assert shown.headers["content-type"] == "image/jpeg"
    assert shown.content == JPEG
    assert len(_stored(tmp_path)) == 1


async def test_replacing_a_receipt_removes_the_old_file(site, seeded_reference_data, tmp_path):
    expense_id = await _new_expense(site, seeded_reference_data)
    await site.put(f"/api/expenses/{expense_id}/receipt", content=JPEG)
    first = _stored(tmp_path)

    await site.put(f"/api/expenses/{expense_id}/receipt", content=PNG)

    assert len(_stored(tmp_path)) == 1 and _stored(tmp_path) != first
    shown = await site.get(f"/api/expenses/{expense_id}/receipt")
    assert shown.headers["content-type"] == "image/png"


async def test_removing_a_receipt_deletes_the_file(site, seeded_reference_data, tmp_path):
    expense_id = await _new_expense(site, seeded_reference_data)
    await site.put(f"/api/expenses/{expense_id}/receipt", content=JPEG)

    removed = await site.delete(f"/api/expenses/{expense_id}/receipt")

    assert removed.status_code == 204
    assert (await site.get(f"/api/expenses/{expense_id}")).json()["has_receipt"] is False
    assert (await site.get(f"/api/expenses/{expense_id}/receipt")).status_code == 404
    assert _stored(tmp_path) == []


async def test_only_photos_of_a_reasonable_size_are_accepted(site, seeded_reference_data, tmp_path):
    expense_id = await _new_expense(site, seeded_reference_data)

    gif = await site.put(f"/api/expenses/{expense_id}/receipt", content=b"GIF89a" + b"0" * 50)
    huge = await site.put(
        f"/api/expenses/{expense_id}/receipt", content=JPEG + b"0" * (10 * 1024 * 1024)
    )

    assert gif.status_code == 422
    assert huge.status_code == 413
    assert _stored(tmp_path) == []


async def test_receipts_need_a_login(site, seeded_reference_data):
    expense_id = await _new_expense(site, seeded_reference_data)
    await site.put(f"/api/expenses/{expense_id}/receipt", content=JPEG)
    site.cookies.clear()

    assert (await site.get(f"/api/expenses/{expense_id}/receipt")).status_code == 401
    assert (await site.put(f"/api/expenses/{expense_id}/receipt", content=JPEG)).status_code == 401


# ---------------------------------------------------------------------------
# Hizli giris
# ---------------------------------------------------------------------------


async def test_quick_entry_records_a_cash_expense_for_today(site, seeded_reference_data):
    result = (await site.post("/api/expenses/quick", json={"text": "500 market"})).json()

    expense = result["expense"]
    assert expense["total"]["minor"] == 50_000
    assert expense["category"]["name"] == "Market"
    assert expense["payment_method_id"] == seeded_reference_data["cash_id"]
    assert expense["transaction_date"] == (await site.get("/api/bootstrap")).json()["today"]
    assert expense["is_shared"] is True


async def test_quick_entry_with_a_prefix_and_personal_tag(site):
    expense = (
        await site.post("/api/expenses/quick", json={"text": "75 mar simit #kisisel"})
    ).json()["expense"]

    assert expense["category"]["name"] == "Market"
    assert expense["description"] == "simit #kisisel"
    assert expense["is_shared"] is False


async def test_quick_entry_asks_for_a_category_it_cannot_match(site, seeded_reference_data):
    result = (await site.post("/api/expenses/quick", json={"text": "250 kahve"})).json()

    assert result["expense"] is None
    assert result["amount_minor"] == 25_000
    assert result["description"] == "kahve"
    assert result["candidate_ids"] == [seeded_reference_data["category_id"]]


async def test_text_without_an_amount_is_not_an_expense(site):
    response = await site.post("/api/expenses/quick", json={"text": "merhaba"})

    assert response.status_code == 422
    assert "500 market" in response.json()["detail"]
