"""Gelir kaydı ve ayın nakit durumu.

Buradaki asıl kural şu: aylık harcama raporu taksitli alışverişi tam tutarıyla
sayar, nakit durumu ise yalnızca o ay **cepten çıkacak** kısmı sayar. İkisinin
karışması, kullanıcıya olduğundan çok daha kötü bir tablo gösterirdi.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import cashflow, income, recurring
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def _earn(session, user, amount, *, when=SEPTEMBER, source="Maaş"):
    return await income.create_income(
        session, user=user, amount=amount, received_date=when, source=source
    )


async def _spend(session, user, fixtures, amount, *, method="cash", count=1, when=SEPTEMBER):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures[method].id,
            category_id=fixtures["category"].id,
            transaction_date=when,
            amount=amount,
            installment_count=count,
        ),
    )


# ---------------------------------------------------------------------------
# Gelir kaydı
# ---------------------------------------------------------------------------


async def test_income_is_stored_in_minor_units(async_session, people):
    record = await _earn(async_session, people["aykut"], "45.000")
    assert record.amount_minor == 4_500_000
    assert record.source == "Maaş"


async def test_deleted_income_leaves_the_total(async_session, people):
    record = await _earn(async_session, people["aykut"], "45.000")
    await _earn(async_session, people["aslihan"], "20.000", source="Ek iş")

    await income.soft_delete_income(async_session, user=people["aykut"], record=record)

    total = await income.monthly_total(async_session, year=2026, month=9)
    assert total == 2_000_000


async def test_income_from_another_month_is_not_counted(async_session, people):
    await _earn(async_session, people["aykut"], "45.000", when=date(2026, 8, 30))
    assert await income.monthly_total(async_session, year=2026, month=9) == 0


# ---------------------------------------------------------------------------
# Nakit durumu
# ---------------------------------------------------------------------------


async def test_position_without_income_still_reports_outflow(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500")

    position = await cashflow.monthly_position(async_session, today=SEPTEMBER)

    assert position.has_income is False
    assert position.cash_spent_minor == 50_000
    assert position.remaining_minor == -50_000


async def test_only_this_months_installment_counts_not_the_whole_purchase(
    async_session, people, fixtures
):
    """12 taksitli bir alışverişin bu aya düşen kısmı tek taksittir."""
    await _earn(async_session, people["aykut"], "45.000")
    await _spend(async_session, people["aykut"], fixtures, "12.000", method="card", count=12)

    # Kart: kesim 10, son odeme 20 Eylul pazar -> 21 Eylul. Ilk taksit bu aya duser.
    position = await cashflow.monthly_position(async_session, today=SEPTEMBER)

    assert position.card_due_minor == 100_000
    assert position.remaining_minor == 4_400_000


async def test_a_pending_fixed_expense_is_counted_before_it_is_recorded(
    async_session, people, fixtures
):
    await _earn(async_session, people["aykut"], "45.000")
    await recurring.create_template(
        async_session,
        user=people["aykut"],
        name="Kira",
        category_id=fixtures["category"].id,
        payment_method_id=fixtures["cash"].id,
        amount="15.000",
        day_of_month=20,
        start_date=date(2026, 9, 1),
    )

    position = await cashflow.monthly_position(async_session, today=SEPTEMBER)

    assert position.expected_recurring_minor == 1_500_000
    assert position.remaining_minor == 3_000_000


async def test_a_recorded_fixed_expense_is_not_counted_twice(
    async_session, people, fixtures
):
    await _earn(async_session, people["aykut"], "45.000")
    await recurring.create_template(
        async_session,
        user=people["aykut"],
        name="Kira",
        category_id=fixtures["category"].id,
        payment_method_id=fixtures["cash"].id,
        amount="15.000",
        day_of_month=1,
        start_date=date(2026, 9, 1),
    )
    await recurring.generate_due(async_session, today=SEPTEMBER)

    position = await cashflow.monthly_position(async_session, today=SEPTEMBER)

    assert position.expected_recurring_minor == 0
    assert position.cash_spent_minor == 1_500_000
    assert position.remaining_minor == 3_000_000


async def test_a_card_template_is_left_out_of_expected_cash(
    async_session, people, fixtures
):
    """Karta yazılan abonelik bu ay değil, ekstresiyle birlikte cepten çıkar."""
    await recurring.create_template(
        async_session,
        user=people["aykut"],
        name="Netflix",
        category_id=fixtures["category"].id,
        payment_method_id=fixtures["card"].id,
        amount="229,90",
        day_of_month=20,
        start_date=date(2026, 9, 1),
    )

    position = await cashflow.monthly_position(async_session, today=SEPTEMBER)

    assert position.expected_recurring_minor == 0
