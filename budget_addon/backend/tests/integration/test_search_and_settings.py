"""Arama ve ayar testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-R8, I-R9, I-L9)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.expenses import ExpenseInput, create_expense, soft_delete_expense
from app.services.search import SearchFilters, search_expenses
from app.services.settings_service import (
    SettingsError,
    create_category,
    create_payment_method,
    list_categories,
    list_payment_methods,
    update_category,
    update_payment_method,
)

pytestmark = pytest.mark.asyncio


async def add(session, user, fixtures, *, method="cash", amount="100",
              description=None, when=date(2026, 9, 5), category=None, count=1):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures[method].id,
            category_id=(category or fixtures["category"]).id,
            transaction_date=when,
            amount=amount,
            installment_count=count,
            description=description,
        ),
    )


# ---------------------------------------------------------------------------
# Arama
# ---------------------------------------------------------------------------


@pytest.fixture()
async def searchable(async_session, people, fixtures):
    await add(async_session, people["aykut"], fixtures,
              amount="250", description="Migros alışverişi")
    await add(async_session, people["aslihan"], fixtures,
              amount="1.400", description="MIGROS büyük alışveriş", when=date(2026, 8, 20))
    await add(async_session, people["aykut"], fixtures, method="card",
              amount="600", description="Benzin", category=fixtures["fuel"])
    await add(async_session, people["aykut"], fixtures, amount="75", description=None)


async def test_i_r8_text_search_is_case_insensitive(async_session, searchable):
    page = await search_expenses(async_session, SearchFilters(text="migros"))
    assert page.total == 2

    upper = await search_expenses(async_session, SearchFilters(text="MIGROS"))
    assert upper.total == 2


async def test_search_matches_the_public_id(async_session, searchable):
    page = await search_expenses(async_session, SearchFilters(text="EXP-000001"))
    assert page.total == 1


async def test_date_range_filter(async_session, searchable):
    page = await search_expenses(
        async_session,
        SearchFilters(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)),
    )
    assert page.total == 3


async def test_category_and_payment_method_filters(async_session, searchable, fixtures):
    by_category = await search_expenses(
        async_session, SearchFilters(category_id=fixtures["fuel"].id)
    )
    assert by_category.total == 1

    by_method = await search_expenses(
        async_session, SearchFilters(payment_method_id=fixtures["card"].id)
    )
    assert by_method.total == 1


async def test_user_filter_separates_the_two_people(async_session, searchable, people):
    aykut = await search_expenses(
        async_session, SearchFilters(created_by_user_id=people["aykut"].id)
    )
    aslihan = await search_expenses(
        async_session, SearchFilters(created_by_user_id=people["aslihan"].id)
    )
    assert aykut.total == 3
    assert aslihan.total == 1


async def test_amount_range_filter(async_session, searchable):
    page = await search_expenses(
        async_session, SearchFilters(min_amount_minor=50_000, max_amount_minor=100_000)
    )
    assert page.total == 1


async def test_i_r9_wildcards_in_the_search_text_are_literal(async_session, searchable):
    """`%` yazan kullanıcı tüm kayıtları getirmemelidir."""
    page = await search_expenses(async_session, SearchFilters(text="%"))
    assert page.total == 0

    underscore = await search_expenses(async_session, SearchFilters(text="_"))
    assert underscore.total == 0


async def test_pagination_splits_results_without_gaps(async_session, searchable):
    first = await search_expenses(async_session, SearchFilters(), page=1, page_size=2)
    second = await search_expenses(async_session, SearchFilters(), page=2, page_size=2)

    assert first.total == 4
    assert first.total_pages == 2
    assert first.has_next is True
    assert second.has_next is False
    assert len(first.items) == 2 and len(second.items) == 2
    assert {e.id for e in first.items}.isdisjoint({e.id for e in second.items})


async def test_deleted_expenses_never_appear_in_search(
    async_session, people, searchable
):
    page = await search_expenses(async_session, SearchFilters(text="migros"))
    await soft_delete_expense(
        async_session, user=people["aykut"], expense=page.items[0]
    )

    after = await search_expenses(async_session, SearchFilters(text="migros"))
    assert after.total == 1


# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------


async def test_card_days_can_be_corrected(async_session, people, fixtures):
    card = fixtures["card"]
    updated = await update_payment_method(
        async_session,
        user=people["aykut"],
        method=card,
        changes={"statement_day": 26, "due_day": 10},
    )
    assert (updated.statement_day, updated.due_day) == (26, 10)


async def test_i_l9_correcting_a_card_does_not_move_existing_installments(
    async_session, people, fixtures
):
    """Ayarları düzeltmek geçmiş taksitleri kaydırmamalıdır."""
    expense = await add(
        async_session, people["aykut"], fixtures, method="card",
        amount="3.000", count=3, when=date(2026, 9, 8),
    )
    before = [(l.amount_minor, l.statement_date, l.due_date) for l in expense.installments]

    await update_payment_method(
        async_session,
        user=people["aykut"],
        method=fixtures["card"],
        changes={"statement_day": 1, "due_day": 15},
    )

    await async_session.refresh(expense, attribute_names=["installments"])
    after = [(l.amount_minor, l.statement_date, l.due_date) for l in expense.installments]
    assert after == before


@pytest.mark.parametrize("changes", [{"statement_day": 0}, {"due_day": 32}])
async def test_invalid_card_days_are_refused(async_session, people, fixtures, changes):
    with pytest.raises(SettingsError):
        await update_payment_method(
            async_session, user=people["aykut"], method=fixtures["card"], changes=changes
        )


async def test_cash_cannot_be_given_statement_days(async_session, people, fixtures):
    with pytest.raises(SettingsError):
        await update_payment_method(
            async_session,
            user=people["aykut"],
            method=fixtures["cash"],
            changes={"statement_day": 10},
        )


async def test_duplicate_names_are_refused(async_session, people, fixtures):
    with pytest.raises(SettingsError):
        await create_payment_method(
            async_session, user=people["aykut"], name="Nakit", type="cash"
        )


async def test_new_card_requires_both_days(async_session, people):
    with pytest.raises(SettingsError):
        await create_payment_method(
            async_session,
            user=people["aykut"],
            name="Yeni Kart",
            type="credit_card",
            statement_day=10,
        )


async def test_deactivated_card_disappears_from_the_active_list(
    async_session, people, fixtures
):
    await update_payment_method(
        async_session, user=people["aykut"], method=fixtures["card"],
        changes={"is_active": False},
    )

    active = await list_payment_methods(async_session)
    everything = await list_payment_methods(async_session, include_inactive=True)
    assert fixtures["card"].id not in {m.id for m in active}
    assert fixtures["card"].id in {m.id for m in everything}


async def test_categories_can_be_added_and_deactivated(async_session, people):
    created = await create_category(
        async_session, user=people["aykut"], name="Abonelikler", emoji="📺"
    )
    assert created.id is not None

    await update_category(
        async_session, user=people["aykut"], category=created, changes={"is_active": False}
    )
    active = await list_categories(async_session)
    assert created.id not in {c.id for c in active}


async def test_settings_changes_are_recorded_in_the_audit_log(
    async_session, people, fixtures, count_rows
):
    from app.models import AuditLog

    before = await count_rows(AuditLog)
    await update_payment_method(
        async_session, user=people["aykut"], method=fixtures["card"],
        changes={"statement_day": 15, "due_day": 25},
    )
    assert await count_rows(AuditLog) == before + 1
