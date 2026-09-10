"""Kişisel yıllık bütçeler.

Kişisel harcama, kimin kartıyla alındığına ve kaydı kimin girdiğine
bakılmaksızın sahibinin bütçesinden düşer ve denkleştirmeye girmez.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import personal_budgets, reports
from app.services.expenses import ExpenseInput, create_expense, update_expense
from app.services.settlement import monthly_settlement

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def _spend(session, user, fixtures, amount, *, owner=None, shared=True, count=1):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=SEPTEMBER,
            amount=amount,
            installment_count=count,
            is_shared=shared,
            owner_user_id=owner,
        ),
    )


def _find(items, user_id):
    return next(item for item in items if item.user_id == user_id)


async def test_a_personal_purchase_counts_against_its_owner_not_the_buyer(
    async_session, people, fixtures
):
    aykut, aslihan = people["aykut"], people["aslihan"]
    await personal_budgets.set_budget(
        async_session, user_id=aslihan.id, year=2026, amount_minor=4_000_000
    )

    # Aykut, Aslihan'in ayakkabisini kendi kartiyla 3 taksitle girer.
    expense = await _spend(
        async_session, aykut, fixtures, "3.000", owner=aslihan.id, count=3
    )
    assert expense.owner_user_id == aslihan.id
    assert expense.is_shared is False

    status = await personal_budgets.yearly_status(
        async_session, year=2026, today=SEPTEMBER
    )
    her = _find(status, aslihan.id)
    assert her.spent_minor == 300_000
    assert her.remaining_minor == 3_700_000
    assert _find(status, aykut.id).spent_minor == 0
    assert _find(status, aykut.id).budget_minor is None


async def test_personal_spending_stays_out_of_the_settlement(async_session, people, fixtures):
    aykut, aslihan = people["aykut"], people["aslihan"]
    await _spend(async_session, aykut, fixtures, "1.000")
    await _spend(async_session, aykut, fixtures, "500", owner=aslihan.id)

    result = await monthly_settlement(async_session, year=2026, month=9)
    assert result.shared_total_minor == 100_000


async def test_unticking_shared_without_an_owner_makes_it_the_entrants(
    async_session, people, fixtures
):
    expense = await _spend(async_session, people["aykut"], fixtures, "200", shared=False)
    assert expense.owner_user_id == people["aykut"].id


async def test_an_expense_can_move_between_shared_and_personal(async_session, people, fixtures):
    aykut, aslihan = people["aykut"], people["aslihan"]
    expense = await _spend(async_session, aykut, fixtures, "750")

    await update_expense(
        async_session, user=aykut, expense=expense, changes={"owner_user_id": aslihan.id}
    )
    assert (expense.owner_user_id, expense.is_shared) == (aslihan.id, False)

    await update_expense(
        async_session, user=aykut, expense=expense, changes={"is_shared": True}
    )
    assert (expense.owner_user_id, expense.is_shared) == (None, True)


async def test_the_spending_report_can_be_narrowed_to_one_owner(
    async_session, people, fixtures
):
    aykut, aslihan = people["aykut"], people["aslihan"]
    await _spend(async_session, aykut, fixtures, "1.000")
    await _spend(async_session, aykut, fixtures, "400", owner=aslihan.id)

    everything = await reports.monthly_spending(async_session, year=2026, month=9)
    shared = await reports.monthly_spending(
        async_session, year=2026, month=9, owner="shared"
    )
    hers = await reports.monthly_spending(
        async_session, year=2026, month=9, owner=str(aslihan.id)
    )
    assert everything.total_minor == 140_000
    assert shared.total_minor == 100_000
    assert hers.total_minor == 40_000


async def test_budgets_do_not_carry_over_between_years(async_session, people, fixtures):
    aslihan = people["aslihan"]
    await personal_budgets.set_budget(
        async_session, user_id=aslihan.id, year=2026, amount_minor=4_000_000
    )
    await _spend(async_session, people["aykut"], fixtures, "1.000", owner=aslihan.id)

    next_year = _find(
        await personal_budgets.yearly_status(
            async_session, year=2027, today=date(2027, 1, 2)
        ),
        aslihan.id,
    )
    assert next_year.budget_minor is None
    assert next_year.spent_minor == 0
