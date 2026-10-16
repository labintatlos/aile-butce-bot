"""Bölünmüş harcama: parçalar tutara eşittir ve her parça kendi kategorisine yazılır."""

from __future__ import annotations

from datetime import date

import pytest

from app.models import Category
from app.services import budgets, exporting, reports, search
from app.services.expenses import (
    ExpenseError,
    ExpenseInput,
    SplitInput,
    create_expense,
    update_expense,
)
from app.services.refunds import create_refund
from app.services.settings_service import SettingsError, delete_category

pytestmark = pytest.mark.asyncio

OCT_5 = date(2026, 10, 5)


async def _split_receipt(session, people, fixtures, cleaning):
    return await create_expense(
        session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=OCT_5,
            amount="1.200",
            description="Migros fişi",
            splits=(
                SplitInput(category_id=fixtures["category"].id, amount="900"),
                SplitInput(category_id=cleaning.id, amount="300", note="deterjan"),
            ),
        ),
    )


@pytest.fixture()
async def cleaning(async_session):
    category = Category(name="Temizlik", emoji="🧽", sort_order=3)
    async_session.add(category)
    await async_session.commit()
    return category


async def test_parts_are_saved_and_the_largest_part_is_the_main_category(
    async_session, people, fixtures, cleaning
):
    expense = await _split_receipt(async_session, people, fixtures, cleaning)

    assert [(part.category_id, part.amount_minor) for part in expense.splits] == [
        (fixtures["category"].id, 90_000),
        (cleaning.id, 30_000),
    ]
    assert expense.category_id == fixtures["category"].id
    assert expense.splits[1].note == "deterjan"


async def test_parts_must_add_up_to_the_total(async_session, people, fixtures, cleaning):
    with pytest.raises(ExpenseError, match="eşit olmalıdır"):
        await create_expense(
            async_session,
            user=people["aykut"],
            data=ExpenseInput(
                payment_method_id=fixtures["cash"].id,
                category_id=fixtures["category"].id,
                transaction_date=OCT_5,
                amount="1.200",
                splits=(
                    SplitInput(category_id=fixtures["category"].id, amount="900"),
                    SplitInput(category_id=cleaning.id, amount="299,99"),
                ),
            ),
        )


async def test_a_single_part_is_not_a_split(async_session, people, fixtures, cleaning):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=OCT_5,
            amount="300",
            splits=(SplitInput(category_id=cleaning.id, amount="300"),),
        ),
    )
    assert expense.splits == []
    assert expense.category_id == cleaning.id


async def test_category_reports_and_budgets_count_each_part(
    async_session, people, fixtures, cleaning
):
    fixtures["category"].monthly_budget_minor = 100_000
    cleaning.monthly_budget_minor = 50_000
    await async_session.commit()
    await _split_receipt(async_session, people, fixtures, cleaning)

    report = await reports.monthly_spending(async_session, year=2026, month=10)
    by_name = {item.name: item.total_minor for item in report.by_category}
    assert by_name == {"Market": 90_000, "Temizlik": 30_000}
    assert report.total_minor == 120_000

    statuses = {
        status.name: status.spent_minor
        for status in await budgets.monthly_status(async_session, year=2026, month=10)
    }
    assert statuses == {"Market": 90_000, "Temizlik": 30_000}


async def test_a_refund_is_shared_between_the_parts(async_session, people, fixtures, cleaning):
    expense = await _split_receipt(async_session, people, fixtures, cleaning)
    await create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount=40_000,
        refund_date=OCT_5,
    )

    report = await reports.monthly_spending(async_session, year=2026, month=10)
    by_name = {item.name: item.total_minor for item in report.by_category}
    assert by_name == {"Market": 60_000, "Temizlik": 20_000}


async def test_changing_the_amount_requires_new_parts(async_session, people, fixtures, cleaning):
    expense = await _split_receipt(async_session, people, fixtures, cleaning)

    with pytest.raises(ExpenseError, match="parçaları da yeniden"):
        await update_expense(
            async_session, user=people["aykut"], expense=expense, changes={"amount": "1.500"}
        )
    with pytest.raises(ExpenseError, match="parçalarından"):
        await update_expense(
            async_session,
            user=people["aykut"],
            expense=expense,
            changes={"category_id": cleaning.id},
        )

    updated = await update_expense(
        async_session,
        user=people["aykut"],
        expense=expense,
        changes={
            "amount": "1.500",
            "splits": [
                {"category_id": fixtures["category"].id, "amount": "500"},
                {"category_id": cleaning.id, "amount": "1.000"},
            ],
        },
    )
    assert updated.total_amount_minor == 150_000
    assert updated.category_id == cleaning.id
    assert sum(part.amount_minor for part in updated.splits) == 150_000


async def test_an_empty_part_list_removes_the_split(async_session, people, fixtures, cleaning):
    expense = await _split_receipt(async_session, people, fixtures, cleaning)
    updated = await update_expense(
        async_session, user=people["aykut"], expense=expense, changes={"splits": []}
    )
    assert updated.splits == []
    assert updated.category_id == fixtures["category"].id


async def test_search_by_category_finds_split_receipts(async_session, people, fixtures, cleaning):
    expense = await _split_receipt(async_session, people, fixtures, cleaning)
    page = await search.search_expenses(
        async_session, search.SearchFilters(category_id=cleaning.id)
    )
    assert [item.id for item in page.items] == [expense.id]


async def test_a_category_used_in_a_part_cannot_be_deleted(
    async_session, people, fixtures, cleaning
):
    await _split_receipt(async_session, people, fixtures, cleaning)
    with pytest.raises(SettingsError, match="kullanılıyor"):
        await delete_category(async_session, user=people["aykut"], category=cleaning)


async def test_the_csv_lists_every_part(async_session, people, fixtures, cleaning):
    await _split_receipt(async_session, people, fixtures, cleaning)
    content = await exporting.expenses_csv(
        async_session, start=date(2026, 10, 1), end=date(2026, 10, 31)
    )
    assert "Market 900,00 + Temizlik 300,00" in content
