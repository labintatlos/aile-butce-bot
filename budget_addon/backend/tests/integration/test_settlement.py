"""Ortak giderlerin denkleştirilmesi.

Denkleştirme yalnızca ortak işaretli harcamaları kapsar ve kuruş kaybetmez:
payların toplamı her zaman ortak toplama eşittir.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import refunds, settlement, tags
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def _spend(session, user, fixtures, amount, *, shared=True, description=None):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=SEPTEMBER,
            amount=amount,
            installment_count=1,
            description=description,
            is_shared=shared,
        ),
    )


def _by_name(report, name):
    return next(person for person in report.balances if person.name == name)


async def test_an_empty_month_is_even(async_session, people):
    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert report.shared_total_minor == 0
    assert report.is_even is True
    assert report.creditor is None


async def test_equal_contributions_leave_nothing_to_settle(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "1.000")
    await _spend(async_session, people["aslihan"], fixtures, "1.000")

    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert report.is_even is True
    assert report.transfer_minor == 0


async def test_the_one_who_paid_more_is_owed_the_difference(
    async_session, people, fixtures
):
    await _spend(async_session, people["aslihan"], fixtures, "3.000")
    await _spend(async_session, people["aykut"], fixtures, "1.000")

    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert report.shared_total_minor == 400_000
    assert _by_name(report, "Aslıhan").share_minor == 200_000
    assert _by_name(report, "Aslıhan").balance_minor == 100_000
    assert _by_name(report, "Aykut").balance_minor == -100_000
    assert report.creditor.name == "Aslıhan"
    assert report.debtor.name == "Aykut"
    assert report.transfer_minor == 100_000


async def test_a_personal_expense_stays_out_of_the_settlement(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "1.000")
    await _spend(async_session, people["aykut"], fixtures, "5.000", shared=False)

    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert report.shared_total_minor == 100_000
    assert _by_name(report, "Aykut").paid_minor == 100_000


async def test_the_personal_tag_marks_an_expense_personal():
    assert tags.marks_personal("kitap #kisisel") is True
    assert tags.marks_personal("kitap #özel") is True
    assert tags.marks_personal("kitap #hediye") is False


async def test_shares_never_lose_a_kurus(async_session, people, fixtures):
    """Tek kuruşluk bir toplam bile bölündüğünde kaybolmamalıdır."""
    await _spend(async_session, people["aykut"], fixtures, "0,01")

    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert sum(person.share_minor for person in report.balances) == 1


async def test_a_refund_lowers_the_payers_contribution(
    async_session, people, fixtures
):
    expense = await _spend(async_session, people["aslihan"], fixtures, "3.000")
    await _spend(async_session, people["aykut"], fixtures, "1.000")
    await refunds.create_refund(
        async_session,
        user=people["aslihan"],
        expense_id=expense.id,
        amount="2.000",
        refund_date=SEPTEMBER,
    )

    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert _by_name(report, "Aslıhan").paid_minor == 100_000
    assert report.is_even is True


async def test_another_months_spending_is_not_mixed_in(
    async_session, people, fixtures
):
    await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 8, 20),
            amount="9.000",
            installment_count=1,
        ),
    )

    report = await settlement.monthly_settlement(async_session, year=2026, month=9)

    assert report.shared_total_minor == 0
