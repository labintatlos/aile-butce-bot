"""CSV dışa aktarma ve yıllık karşılaştırma.

CSV'nin biçimi Türkçe Excel'e göre seçildi: noktalı virgül ayraç, virgüllü
ondalık ve UTF-8 BOM. Bunlardan biri bozulursa dosya tek sütuna yapışır ya da
Türkçe karakterler bozulur, ikisi de sessizce olur.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import exporting, income, refunds, reports
from app.services.expenses import ExpenseInput, create_expense

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
# Biçim
# ---------------------------------------------------------------------------


async def test_amounts_use_a_comma_and_no_thousands_separator():
    assert exporting.format_amount(1_234_56) == "1234,56"
    assert exporting.format_amount(50) == "0,50"
    assert exporting.format_amount(0) == "0,00"
    assert exporting.format_amount(-150) == "-1,50"


async def test_the_file_starts_with_a_bom_and_uses_semicolons(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500")

    content = await exporting.expenses_csv(
        async_session, start=date(2026, 9, 1), end=date(2026, 9, 30)
    )

    assert content.startswith("﻿")
    header = content.splitlines()[0]
    assert header.count(";") == len(exporting.EXPENSE_HEADERS) - 1


async def test_a_row_carries_the_net_amount_and_the_tags(
    async_session, people, fixtures
):
    expense = await _spend(
        async_session, people["aykut"], fixtures, "1.000", "market #bodrum"
    )
    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=SEPTEMBER,
    )

    content = await exporting.expenses_csv(
        async_session, start=date(2026, 9, 1), end=date(2026, 9, 30)
    )
    row = content.splitlines()[1].split(";")

    assert row[0] == expense.public_id
    assert row[2] == "1000,00"
    assert row[3] == "400,00"
    assert row[4] == "600,00"
    assert row[8] == "Aykut"
    assert "#bodrum" in row[10]


async def test_only_the_requested_range_is_exported(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500", when=date(2026, 8, 31))
    await _spend(async_session, people["aykut"], fixtures, "600", when=SEPTEMBER)

    content = await exporting.expenses_csv(
        async_session, start=date(2026, 9, 1), end=date(2026, 9, 30)
    )

    assert len(content.splitlines()) == 2  # baslik + tek kayit


async def test_incomes_export_separately(async_session, people):
    await income.create_income(
        async_session,
        user=people["aykut"],
        amount="45.000",
        received_date=SEPTEMBER,
        source="Maaş",
    )

    content = await exporting.incomes_csv(
        async_session, start=date(2026, 9, 1), end=date(2026, 9, 30)
    )
    row = content.splitlines()[1].split(";")

    assert row[1] == "45000,00"
    assert row[2] == "Maaş"


async def test_the_file_name_says_the_period():
    assert exporting.filename_for(year=2026, month=9) == "butce-harcama-2026-09.csv"
    assert exporting.filename_for(year=2026, month=None) == "butce-harcama-2026.csv"


# ---------------------------------------------------------------------------
# Yıllık karşılaştırma
# ---------------------------------------------------------------------------


async def test_months_are_compared_with_the_same_month_last_year(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "1.000", when=date(2025, 9, 5))
    await _spend(async_session, people["aykut"], fixtures, "1.500", when=SEPTEMBER)

    comparison = await reports.yearly_comparison(async_session, year=2026)
    september = comparison.months[8]

    assert september.this_year_minor == 150_000
    assert september.last_year_minor == 100_000
    assert september.change_percent == 50


async def test_a_month_without_last_years_record_has_no_percentage(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "1.500", when=SEPTEMBER)

    comparison = await reports.yearly_comparison(async_session, year=2026)

    assert comparison.months[8].change_percent is None


async def test_yearly_totals_are_net_of_refunds(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures, "1.000")
    await refunds.create_refund(
        async_session,
        user=people["aykut"],
        expense_id=expense.id,
        amount="400",
        refund_date=SEPTEMBER,
    )

    comparison = await reports.yearly_comparison(async_session, year=2026)

    assert comparison.this_year_total_minor == 60_000


async def test_the_busiest_month_is_reported(async_session, people, fixtures):
    await _spend(async_session, people["aykut"], fixtures, "500", when=date(2026, 3, 4))
    await _spend(async_session, people["aykut"], fixtures, "2.000", when=SEPTEMBER)

    comparison = await reports.yearly_comparison(async_session, year=2026)

    assert comparison.busiest_month.month == 9
