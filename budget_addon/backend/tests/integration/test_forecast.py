"""Ay sonu tahmini.

Tahmin deterministiktir ve iki ayrı kalemden oluşur: bilinen sabit giderler ve
kestirilen değişken harcama. Asıl sınanan şey sabit giderin iki kez
sayılmaması ve tahminin gerçekleşenin altına düşmemesidir.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import forecast, recurring
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio


async def _spend(session, user, fixtures, amount, *, when):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=when,
            amount=amount,
            installment_count=1,
        ),
    )


async def test_an_empty_month_forecasts_nothing(async_session):
    estimate = await forecast.month_forecast(async_session, today=date(2026, 9, 10))

    assert estimate.total_minor == 0
    assert estimate.has_history is False


async def test_the_run_rate_projects_the_month_from_the_days_so_far(
    async_session, people, fixtures
):
    """10 günde 3.000 harcandıysa 30 günlük eylülde hız 9.000'dir."""
    await _spend(async_session, people["aykut"], fixtures, "3.000", when=date(2026, 9, 3))

    estimate = await forecast.month_forecast(async_session, today=date(2026, 9, 10))

    assert estimate.days_in_month == 30
    assert estimate.variable_run_rate_minor == 900_000
    # Gecmis ay yok: tahmin yalnizca hiza dayanir.
    assert estimate.variable_forecast_minor == 900_000


async def test_history_pulls_the_early_month_forecast_towards_the_average(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "10.000", when=date(2026, 8, 5))
    await _spend(async_session, people["aykut"], fixtures, "100", when=date(2026, 9, 2))

    estimate = await forecast.month_forecast(async_session, today=date(2026, 9, 2))

    # Ayin 2'sinde bu ayin hizi (1.500) tek basina anlamsizdir; gecmis ayin
    # 10.000'i tahmini yukari ceker.
    assert estimate.variable_history_minor == 1_000_000
    assert estimate.variable_forecast_minor > estimate.variable_run_rate_minor


async def test_late_in_the_month_this_months_own_pace_dominates(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "10.000", when=date(2026, 8, 5))
    await _spend(async_session, people["aykut"], fixtures, "2.900", when=date(2026, 9, 5))

    early = await forecast.month_forecast(async_session, today=date(2026, 9, 5))
    late = await forecast.month_forecast(async_session, today=date(2026, 9, 28))

    assert abs(late.variable_forecast_minor - late.variable_run_rate_minor) < abs(
        early.variable_forecast_minor - early.variable_run_rate_minor
    )


async def test_a_fixed_cost_is_counted_once_not_projected(
    async_session, people, fixtures
):
    """Kira hem kayıtta hem günlük hızda sayılırsa tahmin şişerdi."""
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
    await recurring.generate_due(async_session, today=date(2026, 9, 1))

    estimate = await forecast.month_forecast(async_session, today=date(2026, 9, 3))

    assert estimate.fixed_minor == 1_500_000
    assert estimate.variable_so_far_minor == 0
    assert estimate.variable_forecast_minor == 0
    assert estimate.total_minor == 1_500_000


async def test_a_fixed_cost_whose_day_has_not_come_is_still_expected(
    async_session, people, fixtures
):
    await recurring.create_template(
        async_session,
        user=people["aykut"],
        name="Kira",
        category_id=fixtures["category"].id,
        payment_method_id=fixtures["cash"].id,
        amount="15.000",
        day_of_month=25,
        start_date=date(2026, 9, 1),
    )

    estimate = await forecast.month_forecast(async_session, today=date(2026, 9, 3))

    assert estimate.fixed_minor == 1_500_000
    assert estimate.spent_so_far_minor == 0
    assert estimate.remaining_minor == 1_500_000


async def test_the_forecast_never_falls_below_what_was_already_spent(
    async_session, people, fixtures
):
    """Ay biterken hız düşse bile tahmin gerçekleşenin altına inmemelidir."""
    await _spend(async_session, people["aykut"], fixtures, "5.000", when=date(2026, 9, 1))

    estimate = await forecast.month_forecast(async_session, today=date(2026, 9, 30))

    assert estimate.variable_forecast_minor >= estimate.variable_so_far_minor
