"""Sabit giderler: şablon yönetimi ve aylık üretim.

Üretimin iki kez çalışmaması ve kayıt tarihinin **şablonun günü** olması bu
özelliğin bel kemiğidir: eklenti üç gün kapalı kalmışsa kira yine ayın 1'ine
yazılmalı, açıldığı güne değil.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import Expense
from app.services import recurring
from app.services.expenses import soft_delete_expense

pytestmark = pytest.mark.asyncio


SEPTEMBER_FIRST = date(2026, 9, 1)


async def _template(
    session, user, fixtures, *, day=1, amount="15.000", name="Kira", start=SEPTEMBER_FIRST
):
    return await recurring.create_template(
        session,
        user=user,
        name=name,
        category_id=fixtures["category"].id,
        payment_method_id=fixtures["cash"].id,
        amount=amount,
        day_of_month=day,
        start_date=start,
    )


async def _count_expenses(session) -> int:
    return await session.scalar(select(func.count()).select_from(Expense))


# ---------------------------------------------------------------------------
# Şablon yönetimi
# ---------------------------------------------------------------------------


async def test_template_stores_the_amount_in_minor_units(
    async_session, people, fixtures
):
    template = await _template(async_session, people["aykut"], fixtures)
    assert template.amount_minor == 1_500_000
    assert template.is_active is True


async def test_day_beyond_the_month_falls_on_the_last_day(
    async_session, people, fixtures
):
    template = await _template(async_session, people["aykut"], fixtures, day=31)
    assert recurring.scheduled_date(template, year=2026, month=2) == date(2026, 2, 28)


async def test_inactive_templates_are_hidden_but_retrievable(
    async_session, people, fixtures
):
    template = await _template(async_session, people["aykut"], fixtures)
    await recurring.update_template(
        async_session, user=people["aykut"], template=template, is_active=False
    )

    assert await recurring.list_templates(async_session) == []
    assert len(await recurring.list_templates(async_session, include_inactive=True)) == 1


# ---------------------------------------------------------------------------
# Üretim
# ---------------------------------------------------------------------------


async def test_expense_is_created_on_the_scheduled_day(
    async_session, people, fixtures
):
    await _template(async_session, people["aykut"], fixtures, day=1)

    generated = await recurring.generate_due(async_session, today=date(2026, 9, 1))

    assert len(generated) == 1
    expense = generated[0].expense
    assert expense.total_amount_minor == 1_500_000
    assert expense.transaction_date == date(2026, 9, 1)
    assert expense.description == "Kira"


async def test_nothing_is_created_before_the_scheduled_day(
    async_session, people, fixtures
):
    await _template(async_session, people["aykut"], fixtures, day=15)

    assert await recurring.generate_due(async_session, today=date(2026, 9, 14)) == []
    assert await _count_expenses(async_session) == 0


async def test_a_late_run_still_records_the_scheduled_day(
    async_session, people, fixtures
):
    """Eklenti kapalı kaldıysa kayıt tarihi kaymaz."""
    await _template(async_session, people["aykut"], fixtures, day=1)

    generated = await recurring.generate_due(async_session, today=date(2026, 9, 5))

    assert generated[0].expense.transaction_date == date(2026, 9, 1)


async def test_the_same_month_is_never_generated_twice(
    async_session, people, fixtures
):
    await _template(async_session, people["aykut"], fixtures, day=1)

    await recurring.generate_due(async_session, today=date(2026, 9, 1))
    again = await recurring.generate_due(async_session, today=date(2026, 9, 20))

    assert again == []
    assert await _count_expenses(async_session) == 1


async def test_a_deleted_generated_expense_does_not_come_back(
    async_session, people, fixtures
):
    """Kullanıcı kaydı sildiyse sistem onu ertesi gün diriltmemelidir."""
    await _template(async_session, people["aykut"], fixtures, day=1)
    generated = await recurring.generate_due(async_session, today=date(2026, 9, 1))
    await soft_delete_expense(
        async_session, user=people["aykut"], expense=generated[0].expense
    )

    assert await recurring.generate_due(async_session, today=date(2026, 9, 2)) == []


async def test_a_missed_previous_month_is_caught_up(async_session, people, fixtures):
    await _template(
        async_session, people["aykut"], fixtures, day=28, start=date(2026, 8, 1)
    )

    generated = await recurring.generate_due(async_session, today=date(2026, 9, 2))

    assert len(generated) == 1
    assert generated[0].expense.transaction_date == date(2026, 8, 28)


async def test_stopped_templates_generate_nothing(async_session, people, fixtures):
    template = await _template(async_session, people["aykut"], fixtures, day=1)
    await recurring.update_template(
        async_session, user=people["aykut"], template=template, is_active=False
    )

    assert await recurring.generate_due(async_session, today=date(2026, 9, 1)) == []


async def test_a_card_template_gets_a_real_installment_schedule(
    async_session, people, fixtures
):
    """Sabit gider de normal harcama yoluyla yazılır; ekstre hesabı çalışır."""
    await recurring.create_template(
        async_session,
        user=people["aykut"],
        name="Spor salonu",
        category_id=fixtures["category"].id,
        payment_method_id=fixtures["card"].id,
        amount="800",
        day_of_month=5,
        start_date=SEPTEMBER_FIRST,
    )

    generated = await recurring.generate_due(async_session, today=date(2026, 9, 5))

    installments = generated[0].expense.installments
    assert len(installments) == 1
    assert installments[0].statement_date == date(2026, 9, 10)


async def test_deleting_a_template_keeps_its_expenses_but_clears_the_link(
    async_session, people, fixtures
):
    template = await _template(async_session, people["aykut"], fixtures, day=1)
    generated = await recurring.generate_due(async_session, today=date(2026, 9, 1))
    expense_id = generated[0].expense.id

    await recurring.delete_template(
        async_session, user=people["aykut"], template=template
    )

    await async_session.commit()
    expense = await async_session.get(Expense, expense_id)
    await async_session.refresh(expense)
    assert expense is not None
    assert expense.recurring_expense_id is None


async def test_changing_the_amount_does_not_touch_past_records(
    async_session, people, fixtures
):
    template = await _template(async_session, people["aykut"], fixtures, day=1)
    generated = await recurring.generate_due(async_session, today=date(2026, 9, 1))

    await recurring.update_template(
        async_session, user=people["aykut"], template=template, amount_minor=1_800_000
    )

    assert generated[0].expense.total_amount_minor == 1_500_000
