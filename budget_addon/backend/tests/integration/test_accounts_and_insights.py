"""Hesaplar ve net varlık, devreden bütçe, hedef önerisi, takvim ve ayrıntılı raporlar."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import AccountEntry, RecurringExpense, SavingsGoal
from app.services import accounts, budgets, insights, upcoming
from app.services.expenses import ExpenseInput, SplitInput, create_expense
from app.services.income import create_income
from app.services.refunds import create_refund
from app.services.settings_service import update_category

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 10, 16)


async def _spend(session, people, fixtures, when, amount, *, category=None, method=None, **extra):
    return await create_expense(
        session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=(method or fixtures["cash"]).id,
            category_id=(category or fixtures["category"]).id,
            transaction_date=when,
            amount=amount,
            **extra,
        ),
    )


# ---------------------------------------------------------------------------
# Hesaplar
# ---------------------------------------------------------------------------


async def test_transfers_move_money_between_accounts_without_spending(
    async_session, people, fixtures
):
    user = people["aykut"]
    bank = await accounts.create_account(
        async_session,
        user=user,
        name="Vadesiz",
        kind="bank",
        opening_balance_minor=10_000_00,
        opening_date=date(2026, 10, 1),
    )
    savings = await accounts.create_account(
        async_session,
        user=user,
        name="Birikim",
        kind="savings",
        opening_balance_minor=None,
        opening_date=date(2026, 10, 1),
    )
    legs = await accounts.transfer(
        async_session,
        user=user,
        from_account_id=bank.id,
        to_account_id=savings.id,
        payment_method_id=None,
        amount_minor=2_500_00,
        when=date(2026, 10, 5),
    )
    assert len(legs) == 2

    result = await accounts.overview(async_session, today=TODAY)
    balances = {item.account.name: item.balance_minor for item in result.accounts}
    assert balances == {"Birikim": 2_500_00, "Vadesiz": 7_500_00}
    assert result.today.assets_minor == 10_000_00

    await accounts.delete_entry(async_session, user=user, entry_id=legs[1].id)
    remaining = (await async_session.scalars(select(AccountEntry))).all()
    assert [entry.kind for entry in remaining] == ["balance"]


async def test_net_worth_subtracts_unpaid_card_installments(async_session, people, fixtures):
    user = people["aykut"]
    bank = await accounts.create_account(
        async_session,
        user=user,
        name="Vadesiz",
        kind="bank",
        opening_balance_minor=20_000_00,
        opening_date=date(2026, 9, 1),
    )
    await _spend(
        async_session, people, fixtures, date(2026, 10, 5), "12.000",
        method=fixtures["card"], installment_count=12,
    )
    result = await accounts.overview(async_session, today=TODAY)
    assert result.today.card_debt_minor == 12_000_00
    assert result.today.net_minor == 8_000_00
    # Eylul sonunda harcama henuz yapilmamisti.
    september = next(point for point in result.history if point.when == date(2026, 9, 30))
    assert september.card_debt_minor == 0

    # Karttan odeme bir transfer ayagidir; harcama sayilmaz.
    await accounts.transfer(
        async_session,
        user=user,
        from_account_id=bank.id,
        to_account_id=None,
        payment_method_id=fixtures["card"].id,
        amount_minor=1_000_00,
        when=TODAY,
    )
    entries = await accounts.list_entries(async_session, bank.id)
    assert entries[0].note == "Kart ödemesi: Aslıhan Kredi Kartı 1"


async def test_transfers_need_a_destination(async_session, people, fixtures):
    bank = await accounts.create_account(
        async_session,
        user=people["aykut"],
        name="Vadesiz",
        kind="bank",
        opening_balance_minor=0,
        opening_date=TODAY,
    )
    with pytest.raises(accounts.AccountError):
        await accounts.transfer(
            async_session,
            user=people["aykut"],
            from_account_id=bank.id,
            to_account_id=bank.id,
            payment_method_id=None,
            amount_minor=100,
            when=TODAY,
        )
    with pytest.raises(accounts.AccountError):
        await accounts.transfer(
            async_session,
            user=people["aykut"],
            from_account_id=bank.id,
            to_account_id=None,
            payment_method_id=None,
            amount_minor=100,
            when=TODAY,
        )


# ---------------------------------------------------------------------------
# Devreden butce ve hedef onerisi
# ---------------------------------------------------------------------------


async def test_unspent_budget_rolls_over_and_overspending_carries_too(
    async_session, people, fixtures
):
    market = fixtures["category"]
    market.monthly_budget_minor = 1_000_00
    await async_session.commit()
    await update_category(
        async_session,
        user=people["aykut"],
        category=market,
        changes={"rollover": True},
        today=date(2026, 8, 20),
    )
    assert market.rollover_since == date(2026, 8, 1)

    await _spend(async_session, people, fixtures, date(2026, 8, 10), "600")  # +400 devreder
    await _spend(async_session, people, fixtures, date(2026, 9, 10), "1.500")  # -500 devreder
    await _spend(async_session, people, fixtures, date(2026, 10, 10), "200")

    status = next(
        item
        for item in await budgets.monthly_status(async_session, year=2026, month=10)
        if item.category_id == market.id
    )
    assert status.carry_in_minor == -100_00
    assert status.available_minor == 900_00
    assert status.remaining_minor == 700_00
    assert not status.is_exceeded


async def test_turning_rollover_off_and_on_starts_fresh(async_session, people, fixtures):
    market = fixtures["category"]
    await update_category(
        async_session, user=people["aykut"], category=market,
        changes={"rollover": True}, today=date(2026, 8, 1),
    )
    await update_category(
        async_session, user=people["aykut"], category=market,
        changes={"rollover": False}, today=date(2026, 9, 1),
    )
    assert market.rollover_since is None
    await update_category(
        async_session, user=people["aykut"], category=market,
        changes={"rollover": True}, today=date(2026, 10, 3),
    )
    assert market.rollover_since == date(2026, 10, 1)


async def test_targets_are_suggested_from_the_average_of_full_months(
    async_session, people, fixtures
):
    await _spend(async_session, people, fixtures, date(2026, 7, 5), "3.000")
    await _spend(async_session, people, fixtures, date(2026, 8, 5), "2.000")
    await _spend(async_session, people, fixtures, date(2026, 9, 5), "2.621,00")
    await _spend(async_session, people, fixtures, date(2026, 10, 5), "9.999")  # bu ay sayilmaz

    suggestions = {
        item.category_id: item
        for item in await budgets.suggest_targets(async_session, today=TODAY, months=3)
    }
    market = suggestions[fixtures["category"].id]
    assert market.average_minor == 2_540_33
    assert market.suggested_minor == 2_550_00
    assert suggestions[fixtures["fuel"].id].suggested_minor is None

    with pytest.raises(ValueError):
        await budgets.suggest_targets(async_session, today=TODAY, months=5)


# ---------------------------------------------------------------------------
# Takvim
# ---------------------------------------------------------------------------


async def test_upcoming_lists_recurring_statements_and_goals(async_session, people, fixtures):
    async_session.add_all(
        [
            RecurringExpense(
                name="Kira",
                category_id=fixtures["category"].id,
                payment_method_id=fixtures["cash"].id,
                amount_minor=15_000_00,
                day_of_month=1,
                start_date=date(2026, 1, 1),
                created_by_user_id=people["aykut"].id,
            ),
            SavingsGoal(
                name="Tatil",
                target_minor=5_000_00,
                saved_minor=1_000_00,
                target_date=date(2026, 11, 10),
            ),
        ]
    )
    await async_session.commit()
    await _spend(
        async_session, people, fixtures, date(2026, 10, 12), "900", method=fixtures["card"]
    )

    events = await upcoming.upcoming(async_session, today=TODAY, days=30)
    summary = [(event.when, event.kind, event.amount_minor) for event in events]

    assert (date(2026, 11, 1), upcoming.KIND_RECURRING, 15_000_00) in summary
    # 12 Ekim harcamasi 10 Kasim ekstresine duser; 25 Ekim kesimi bos gelir.
    assert (date(2026, 11, 10), upcoming.KIND_STATEMENT, 900_00) in summary
    assert (date(2026, 10, 25), upcoming.KIND_STATEMENT, 0) in summary
    assert (date(2026, 11, 10), upcoming.KIND_GOAL, 4_000_00) in summary
    assert [event.when for event in events] == sorted(event.when for event in events)


# ---------------------------------------------------------------------------
# Ayrintili raporlar
# ---------------------------------------------------------------------------


async def test_the_category_matrix_nets_refunds_and_honours_splits(
    async_session, people, fixtures
):
    fixtures["fuel"].group_name = "Ulaşım"
    await async_session.commit()
    split = await _spend(
        async_session, people, fixtures, date(2026, 3, 4), "1.000",
        splits=(
            SplitInput(category_id=fixtures["category"].id, amount="700"),
            SplitInput(category_id=fixtures["fuel"].id, amount="300"),
        ),
    )
    await create_refund(
        async_session, user=people["aykut"], expense_id=split.id, amount=10_000,
        refund_date=date(2026, 4, 2),
    )

    matrix = await insights.category_matrix(async_session, year=2026)
    rows = {row.name: row for row in matrix.rows}
    assert rows["Market"].months[2] == 700_00
    assert rows["Market"].months[3] == -70_00
    assert rows["Yakıt"].group_name == "Ulaşım"
    assert rows["Market"].group_name == insights.UNGROUPED
    assert matrix.total_minor == 900_00


async def test_cashflow_history_and_daily_spending(async_session, people, fixtures):
    await create_income(
        async_session, user=people["aykut"], amount=40_000_00,
        received_date=date(2026, 10, 1), source="Maaş",
    )
    await _spend(async_session, people, fixtures, date(2026, 10, 3), "500")
    await _spend(async_session, people, fixtures, date(2026, 10, 3), "250")

    history = await insights.cashflow_history(async_session, today=TODAY, months=3)
    assert [(row.month, row.income_minor, row.spending_minor) for row in history] == [
        (8, 0, 0),
        (9, 0, 0),
        (10, 40_000_00, 750_00),
    ]
    daily = await insights.daily_spending(async_session, year=2026, month=10)
    assert len(daily.days) == 31
    assert daily.days[2] == 750_00

    flow = await insights.money_flow(async_session, year=2026, month=10)
    assert [node.name for node in flow.sources] == ["Maaş"]
    assert flow.remaining_minor == 40_000_00 - 750_00
