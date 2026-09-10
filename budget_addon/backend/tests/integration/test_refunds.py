"""İadeler: tam ve kısmi para iadesi.

En önemli kural: harcamanın taksit planına dokunulmaz. Alışveriş gerçekten
oldu ve ekstreye girdi; iade ayrı bir alacak olarak düşülür. Testler bunu ve
iadenin bütün raporlara aynı şekilde yansımasını sınar.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import budgets, cards, cashflow, refunds, reports
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


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
# Kayıt kuralları
# ---------------------------------------------------------------------------


async def test_a_refund_leaves_the_instalment_plan_untouched(
    async_session, people, fixtures
):
    expense = await _spend(
        async_session, people["aykut"], fixtures, "1.200", method="card", count=12
    )
    before = [line.amount_minor for line in expense.installments]

    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="600",
        refund_date=date(2026, 9, 8),
    )

    await async_session.refresh(expense, attribute_names=["installments"])
    assert [line.amount_minor for line in expense.installments] == before
    assert expense.total_amount_minor == 120_000


async def test_partial_refunds_accumulate(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000")

    for amount in ("300", "200"):
        await refunds.create_refund(
            async_session,
            user=people["aykut"],
            expense_id=expense.id,
            amount=amount,
            refund_date=SEPTEMBER,
        )

    assert await refunds.refunded_total(async_session, expense.id) == 50_000


async def test_a_refund_may_not_exceed_the_expense(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000")

    with pytest.raises(refunds.RefundError):
        await refunds.create_refund(
            async_session,
            user=people["aykut"],
            expense_id=expense.id,
            amount="1.001",
            refund_date=SEPTEMBER,
        )


async def test_a_card_refund_is_credited_to_the_statement_that_follows_it(
    async_session, people, fixtures
):
    """Kart: kesim günü 10. 8 Eylül'deki iade 10 Eylül ekstresine yazılır."""
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000", method="card")

    refund = await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=date(2026, 9, 8),
    )

    assert refund.statement_date == date(2026, 9, 10)
    assert refund.due_date == date(2026, 9, 21)


async def test_a_cash_refund_has_no_statement(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures, "500")

    refund = await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="500",
        refund_date=SEPTEMBER,
    )

    assert refund.statement_date is None
    assert refund.due_date is None


async def test_a_deleted_refund_stops_counting(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000")
    refund = await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=SEPTEMBER,
    )

    await refunds.soft_delete_refund(async_session, user=people["aykut"], refund=refund)

    assert await refunds.refunded_total(async_session, expense.id) == 0


# ---------------------------------------------------------------------------
# Raporlara yansıma
# ---------------------------------------------------------------------------


async def test_the_monthly_report_shows_net_spending(
    async_session, people, fixtures
):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000")
    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=SEPTEMBER,
    )

    report = await reports.monthly_spending(async_session, year=2026, month=9)

    assert report.total_minor == 60_000
    assert report.refunded_minor == 40_000
    assert report.cash_total_minor == 60_000
    assert report.by_category[0].total_minor == 60_000


async def test_a_refund_relieves_the_category_budget(
    async_session, people, fixtures
):
    fixtures["category"].monthly_budget_minor = 100_000
    await async_session.commit()
    expense = await _spend(async_session, people["aykut"], fixtures, "1.200")

    before = (await budgets.monthly_status(async_session, year=2026, month=9))[0]
    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=SEPTEMBER,
    )
    after = (await budgets.monthly_status(async_session, year=2026, month=9))[0]

    assert before.is_exceeded is True
    assert after.is_exceeded is False
    assert after.spent_minor == 80_000


async def test_a_refund_frees_the_committed_card_limit(
    async_session, people, fixtures
):
    fixtures["card"].credit_limit_minor = 1_000_000
    await async_session.commit()
    expense = await _spend(
        async_session, people["aykut"], fixtures, "1.200", method="card", count=12
    )

    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="600",
        refund_date=date(2026, 9, 8),
    )

    usage = next(
        item
        for item in await cards.card_usage(async_session, today=SEPTEMBER)
        if item.name == fixtures["card"].name
    )
    assert usage.outstanding_minor == 60_000


async def test_a_refund_reduces_the_statement_total(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000", method="card")

    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=date(2026, 9, 8),
    )

    statements = await reports.upcoming_statements(async_session, since=SEPTEMBER)
    september = next(
        row for row in statements if row.statement_date == date(2026, 9, 10)
    )
    assert september.total_minor == 60_000


async def test_a_refund_reduces_the_months_cash_outflow(
    async_session, people, fixtures
):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000")
    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=SEPTEMBER,
    )

    position = await cashflow.monthly_position(async_session, today=SEPTEMBER)

    assert position.cash_spent_minor == 60_000
    assert position.outflow_minor == 60_000
