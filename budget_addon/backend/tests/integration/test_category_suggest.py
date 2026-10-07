"""Açıklamadan kategori önerisi: geçmiş kayıtlara dayanan sözlük araması."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.category_suggest import normalise, suggest_category
from app.services.expenses import ExpenseInput, create_expense, soft_delete_expense
from tests.integration.test_receipt_upload import site  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio

DAY = date(2026, 9, 5)


async def _spend(session, user, fixtures, description, category="category"):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures[category].id,
            transaction_date=DAY,
            amount="100",
            description=description,
        ),
    )


def test_descriptions_are_compared_without_case_accents_or_tags():
    assert normalise("  MİGROS  Şube #ev ") == "migros sube"
    assert normalise("#sadece-etiket") == ""
    assert normalise(None) == ""


async def test_the_same_description_brings_back_its_category(async_session, people, fixtures):
    await _spend(async_session, people["aykut"], fixtures, "Shell", category="fuel")

    suggested = await suggest_category(async_session, "shell")

    assert suggested is not None and suggested.id == fixtures["fuel"].id


async def test_the_most_recent_choice_wins(async_session, people, fixtures):
    await _spend(async_session, people["aykut"], fixtures, "migros", category="fuel")
    await _spend(async_session, people["aslihan"], fixtures, "Migros", category="category")

    suggested = await suggest_category(async_session, "migros")

    assert suggested is not None and suggested.id == fixtures["category"].id


async def test_an_exact_match_beats_a_newer_first_word_match(async_session, people, fixtures):
    await _spend(async_session, people["aykut"], fixtures, "migros", category="category")
    await _spend(async_session, people["aykut"], fixtures, "migros benzin", category="fuel")

    suggested = await suggest_category(async_session, "Migros")

    assert suggested is not None and suggested.id == fixtures["category"].id


async def test_the_first_word_is_enough_when_nothing_matches_exactly(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "opet", category="fuel")

    suggested = await suggest_category(async_session, "opet tam depo #tatil")

    assert suggested is not None and suggested.id == fixtures["fuel"].id


async def test_short_or_numeric_first_words_are_not_guessed_from(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "ev temizliği", category="fuel")
    await _spend(async_session, people["aykut"], fixtures, "2026 aidat", category="fuel")

    assert await suggest_category(async_session, "ev eşyası") is None
    assert await suggest_category(async_session, "2026 sigorta") is None


async def test_nothing_is_suggested_without_history(async_session, people, fixtures):
    assert await suggest_category(async_session, "kahve") is None
    assert await suggest_category(async_session, "") is None


async def test_deleted_expenses_and_inactive_categories_are_ignored(
    async_session, people, fixtures
):
    expense = await _spend(async_session, people["aykut"], fixtures, "kırtasiye", "fuel")
    await soft_delete_expense(async_session, user=people["aykut"], expense=expense)
    assert await suggest_category(async_session, "kirtasiye") is None

    await _spend(async_session, people["aykut"], fixtures, "bilet", category="fuel")
    fixtures["fuel"].is_active = False
    await async_session.commit()
    assert await suggest_category(async_session, "bilet") is None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def _record(client, reference, description):
    bootstrap = (await client.get("/api/bootstrap")).json()
    response = await client.post(
        "/api/expenses",
        json={
            "payment_method_id": reference["cash_id"],
            "category_id": reference["category_id"],
            "transaction_date": bootstrap["today"],
            "amount": "80",
            "description": description,
        },
    )
    assert response.status_code == 201, response.text


async def test_the_site_asks_for_a_suggestion(site, seeded_reference_data):  # noqa: F811
    empty = (await site.get("/api/categories/suggest", params={"description": "a101"})).json()
    assert empty == {"category_id": None}

    await _record(site, seeded_reference_data, "A101")
    found = (await site.get("/api/categories/suggest", params={"description": "a101"})).json()

    assert found == {"category_id": seeded_reference_data["category_id"]}


async def test_quick_entry_suggests_but_does_not_record(site, seeded_reference_data):  # noqa: F811
    await _record(site, seeded_reference_data, "simit")
    before = (await site.get("/api/expenses")).json()["total"]

    result = (await site.post("/api/expenses/quick", json={"text": "15 simit"})).json()

    assert result["expense"] is None
    assert result["suggested_category_id"] == seeded_reference_data["category_id"]
    assert (await site.get("/api/expenses")).json()["total"] == before


async def test_suggestions_need_a_login(public_client):
    response = await public_client.get("/api/categories/suggest", params={"description": "x"})
    assert response.status_code == 401
