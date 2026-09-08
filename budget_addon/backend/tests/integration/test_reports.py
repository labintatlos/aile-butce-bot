"""Rapor testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-R*) ve §40 (A-3, A-4)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.expenses import ExpenseInput, create_expense, soft_delete_expense
from app.services.reports import (
    BASIS_DUE,
    BASIS_STATEMENT,
    active_installment_plans,
    future_obligations,
    monthly_spending,
    upcoming_statements,
)

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def add(session, user, fixtures, *, method, amount, count=1, category=None, when=SEPTEMBER):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures[method].id,
            category_id=(category or fixtures["category"]).id,
            transaction_date=when,
            amount=amount,
            installment_count=count,
        ),
    )


@pytest.fixture()
async def september_data(async_session, people, fixtures):
    """§40'taki senaryo: 12.000/12 taksit + 1.000 peşin + 500 nakit."""
    television = await add(
        async_session, people["aykut"], fixtures, method="card", amount="12.000", count=12
    )
    upfront = await add(
        async_session, people["aslihan"], fixtures, method="card", amount="1.000"
    )
    cash = await add(
        async_session,
        people["aslihan"],
        fixtures,
        method="cash",
        amount="500",
        category=fixtures["fuel"],
    )
    return {"television": television, "upfront": upfront, "cash": cash}


# ---------------------------------------------------------------------------
# §40 kabul testi
# ---------------------------------------------------------------------------


async def test_a3_monthly_spending_uses_the_full_expense_amount(
    async_session, september_data
):
    report = await monthly_spending(async_session, year=2026, month=9)

    # 12.000 + 1.000 + 500 = 13.500 TL
    assert report.total_minor == 1_350_000
    assert report.transaction_count == 3


async def test_a4_cash_flow_only_counts_the_installment_that_falls_due(
    async_session, september_data
):
    obligations = await future_obligations(
        async_session, start=date(2026, 9, 1), months=1, basis=BASIS_STATEMENT
    )

    # Eylul ekstresi: televizyonun yalnizca 1 taksiti (1.000) + pesin
    # alisveris (1.000) = 2.000 TL. Nakit harcama gelecek bir borc olmadigi
    # icin bu rapora girmez.
    assert obligations[0].total_minor == 200_000
    # Kritik nokta: harcama raporundaki 13.500 ile ayni sayi degildir.
    assert obligations[0].total_minor != 1_350_000


async def test_spending_and_cash_flow_must_never_be_added_together(
    async_session, september_data
):
    spending = await monthly_spending(async_session, year=2026, month=9)
    cash_flow = await future_obligations(
        async_session, start=date(2026, 9, 1), months=1, basis=BASIS_STATEMENT
    )
    assert spending.total_minor > cash_flow[0].total_minor


# ---------------------------------------------------------------------------
# I-R1, I-R2: aylik rapor kirilimlari
# ---------------------------------------------------------------------------


async def test_i_r1_monthly_report_breakdowns(async_session, september_data):
    report = await monthly_spending(async_session, year=2026, month=9)

    assert report.cash_total_minor == 50_000
    assert report.card_total_minor == 1_300_000
    assert report.largest_expense.total_amount_minor == 1_200_000
    assert report.largest_category.name == "Market"
    assert {c.name for c in report.by_category} == {"Market", "Yakıt"}


async def test_i_r2_person_totals_add_up_to_the_family_total(
    async_session, september_data
):
    report = await monthly_spending(async_session, year=2026, month=9)

    assert {u.name for u in report.by_user} == {"Aykut", "Aslıhan"}
    assert sum(u.total_minor for u in report.by_user) == report.total_minor


async def test_expenses_from_other_months_are_excluded(
    async_session, people, fixtures, september_data
):
    await add(
        async_session,
        people["aykut"],
        fixtures,
        method="cash",
        amount="9.999",
        when=date(2026, 8, 20),
    )
    report = await monthly_spending(async_session, year=2026, month=9)
    assert report.total_minor == 1_350_000


# ---------------------------------------------------------------------------
# I-R3: yumusak silme her raporda gecerli
# ---------------------------------------------------------------------------


async def test_i_r3_soft_deleted_expense_disappears_from_every_report(
    async_session, people, september_data
):
    await soft_delete_expense(
        async_session, user=people["aykut"], expense=september_data["television"]
    )

    spending = await monthly_spending(async_session, year=2026, month=9)
    statements = await upcoming_statements(async_session, since=date(2026, 9, 1))
    plans = await active_installment_plans(async_session)
    obligations = await future_obligations(
        async_session, start=date(2026, 9, 1), months=12
    )

    assert spending.total_minor == 150_000  # 1.000 + 500
    assert all(s.total_minor == 100_000 for s in statements)
    assert plans == []
    # Silinen televizyon dustukten sonra geriye yalnizca pesin kart
    # alisverisi kalir; nakit bu rapora zaten girmez.
    assert sum(o.total_minor for o in obligations) == 100_000


# ---------------------------------------------------------------------------
# I-R4: ekstre raporu
# ---------------------------------------------------------------------------


async def test_i_r4_statement_report_groups_by_card_and_date(
    async_session, people, fixtures, september_data
):
    await add(
        async_session, people["aykut"], fixtures, method="other_card", amount="2.000"
    )

    statements = await upcoming_statements(
        async_session, since=date(2026, 9, 1), until=date(2026, 9, 30)
    )

    by_card = {s.payment_method_name: s for s in statements}
    assert by_card["Aslıhan Kredi Kartı 1"].statement_date == date(2026, 9, 10)
    # 10 Eylul + 10 gun = 20 Eylul, pazar -> 21 Eylul pazartesi
    assert by_card["Aslıhan Kredi Kartı 1"].due_date == date(2026, 9, 21)
    assert by_card["Aslıhan Kredi Kartı 1"].total_minor == 200_000  # 1.000 + 1.000
    assert by_card["Aykut Kredi Kartı 1"].statement_date == date(2026, 9, 25)
    assert by_card["Aykut Kredi Kartı 1"].due_date == date(2026, 10, 5)
    assert by_card["Aykut Kredi Kartı 1"].total_minor == 200_000


async def test_cash_expenses_never_appear_in_the_statement_report(
    async_session, september_data
):
    statements = await upcoming_statements(async_session, since=date(2026, 1, 1))
    assert all(s.total_minor != 50_000 for s in statements)


# ---------------------------------------------------------------------------
# I-R5, I-R6: aktif taksitler
# ---------------------------------------------------------------------------


async def test_i_r5_active_plan_reports_progress_and_remaining_debt(
    async_session, september_data
):
    plans = await active_installment_plans(async_session)

    assert len(plans) == 1
    television = plans[0]
    assert television.total_minor == 1_200_000
    assert television.installment_count == 12
    assert television.paid_position == "0/12"
    assert television.remaining_minor == 1_200_000
    assert television.monthly_minor == 100_000


async def test_i_r6_a_fully_settled_plan_leaves_the_active_list(
    async_session, september_data
):
    from app.models.installment import STATUS_PAID

    television = september_data["television"]
    for line in television.installments:
        line.status = STATUS_PAID
    await async_session.commit()

    assert await active_installment_plans(async_session) == []


async def test_partially_paid_plan_reports_the_right_remainder(
    async_session, september_data
):
    from app.models.installment import STATUS_PAID

    television = september_data["television"]
    for line in television.installments[:4]:
        line.status = STATUS_PAID
    await async_session.commit()

    plan = (await active_installment_plans(async_session))[0]
    assert plan.paid_position == "4/12"
    assert plan.remaining_minor == 800_000


async def test_single_payment_expenses_are_not_installment_plans(
    async_session, september_data
):
    plans = await active_installment_plans(async_session)
    assert all(plan.installment_count > 1 for plan in plans)


# ---------------------------------------------------------------------------
# I-R7: gelecek yuk
# ---------------------------------------------------------------------------


async def test_i_r7_forecast_covers_twelve_months_including_empty_ones(
    async_session, september_data
):
    obligations = await future_obligations(
        async_session, start=date(2026, 9, 1), months=12
    )

    assert len(obligations) == 12
    assert (obligations[0].year, obligations[0].month) == (2026, 9)
    assert (obligations[-1].year, obligations[-1].month) == (2027, 8)
    # Televizyonun 12 taksiti tum aylara yayilir.
    assert all(o.total_minor >= 100_000 for o in obligations)


async def test_statement_and_due_views_shift_the_same_debt(
    async_session, people, fixtures
):
    # Kesim 25, son odeme 5: ekstre Eylul'de, son odeme Ekim'de.
    await add(async_session, people["aykut"], fixtures, method="other_card", amount="1.000")

    by_statement = await future_obligations(
        async_session, start=date(2026, 9, 1), months=2, basis=BASIS_STATEMENT
    )
    by_due = await future_obligations(
        async_session, start=date(2026, 9, 1), months=2, basis=BASIS_DUE
    )

    assert by_statement[0].total_minor == 100_000
    assert by_statement[1].total_minor == 0
    assert by_due[0].total_minor == 0
    assert by_due[1].total_minor == 100_000
    # Toplam borc degismez, yalnizca aylara dagilimi degisir.
    assert sum(o.total_minor for o in by_statement) == sum(o.total_minor for o in by_due)


async def test_cash_is_excluded_from_the_debt_forecast_by_default(
    async_session, september_data
):
    """Nakit gelecek borc degildir; ancak istenirse acikca dahil edilebilir."""
    without_cash = await future_obligations(
        async_session, start=date(2026, 9, 1), months=1
    )
    with_cash = await future_obligations(
        async_session, start=date(2026, 9, 1), months=1, include_cash=True
    )

    assert without_cash[0].total_minor == 200_000
    assert with_cash[0].total_minor == 250_000


async def test_forecast_rejects_an_unknown_basis(async_session):
    with pytest.raises(ValueError):
        await future_obligations(async_session, start=date(2026, 9, 1), basis="ay")


async def test_year_boundary_is_handled_in_the_forecast(async_session, september_data):
    obligations = await future_obligations(
        async_session, start=date(2026, 11, 1), months=3
    )
    assert [(o.year, o.month) for o in obligations] == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
    ]
