"""Etiketler: farklı kategorilerdeki harcamaları tek olayda toplamak.

Etiket ayrı bir alan değildir; açıklamanın içinden çıkarılır. Bu yüzden asıl
sınanan şey, çıkarmanın deterministik olması ve açıklama değişince etiketlerin
geride kalmamasıdır.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import tags
from app.services.expenses import (
    ExpenseInput,
    create_expense,
    soft_delete_expense,
    update_expense,
)

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def _spend(session, user, fixtures, amount, description=None, *, when=SEPTEMBER):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=when,
            amount=amount,
            installment_count=1,
            description=description,
        ),
    )


# ---------------------------------------------------------------------------
# Çıkarma
# ---------------------------------------------------------------------------


async def test_tags_are_read_from_the_description():
    assert tags.extract_tags("market alışverişi #bodrum #tatil") == ["bodrum", "tatil"]


async def test_turkish_letters_survive_and_case_is_folded():
    assert tags.extract_tags("#Yakıt #YAKIT #yakit") == ["yakit"]


async def test_text_without_tags_yields_nothing():
    assert tags.extract_tags("market alışverişi") == []
    assert tags.extract_tags(None) == []


# ---------------------------------------------------------------------------
# Harcamaya bağlanma
# ---------------------------------------------------------------------------


async def test_creating_an_expense_stores_its_tags(async_session, people, fixtures):
    expense = await _spend(
        async_session, people["aykut"], fixtures, "500", "market #bodrum"
    )

    assert await tags.tags_of(async_session, expense.id) == ["bodrum"]


async def test_editing_the_description_replaces_the_old_tags(
    async_session, people, fixtures
):
    expense = await _spend(
        async_session, people["aykut"], fixtures, "500", "market #bodrum"
    )

    await update_expense(
        async_session,
        user=people["aykut"],
        expense=expense,
        changes={"description": "market #antalya"},
    )

    assert await tags.tags_of(async_session, expense.id) == ["antalya"]


async def test_totals_gather_different_categories_under_one_tag(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500", "market #bodrum")
    await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["fuel"].id,
            transaction_date=SEPTEMBER,
            amount="1.200",
            installment_count=1,
            description="benzin #bodrum",
        ),
    )

    total = await tags.total_for(async_session, "bodrum")

    assert total.total_minor == 170_000
    assert total.transaction_count == 2


async def test_a_tag_spanning_two_months_is_not_cut_at_the_month_boundary(
    async_session, people, fixtures
):
    await _spend(
        async_session, people["aykut"], fixtures, "500", "#bodrum", when=date(2026, 8, 30)
    )
    await _spend(
        async_session, people["aykut"], fixtures, "300", "#bodrum", when=date(2026, 9, 2)
    )

    assert (await tags.total_for(async_session, "bodrum")).total_minor == 80_000

    only_september = await tags.totals(async_session, year=2026, month=9)
    assert only_september[0].total_minor == 30_000


async def test_a_deleted_expense_leaves_the_tag_total(
    async_session, people, fixtures
):
    expense = await _spend(async_session, people["aykut"], fixtures, "500", "#bodrum")

    await soft_delete_expense(async_session, user=people["aykut"], expense=expense)

    assert (await tags.total_for(async_session, "bodrum")).total_minor == 0


async def test_an_unused_tag_reports_zero(async_session):
    total = await tags.total_for(async_session, "#hicyok")
    assert total.total_minor == 0
    assert total.transaction_count == 0


async def test_the_hash_prefix_is_optional_when_asking(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500", "#bodrum")

    with_hash = await tags.total_for(async_session, "#bodrum")
    without_hash = await tags.total_for(async_session, "bodrum")

    assert with_hash == without_hash


async def test_the_personal_tag_marks_an_expense_personal():
    assert tags.marks_personal("kitap #kisisel") is True
    assert tags.marks_personal("kitap #özel") is True
    assert tags.marks_personal("kitap #hediye") is False
