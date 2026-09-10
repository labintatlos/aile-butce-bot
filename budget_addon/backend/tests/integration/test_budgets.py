"""Kategori bütçe hedefleri.

Hedef bir sınır değildir: aşıldığında kayıt engellenmez, yalnızca haber
verilir. Testler bunu ve eşiklerin ayda bir kez duyurulmasını sınar.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services import scheduler
from app.services import budgets
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def _spend(session, user, fixtures, amount, *, category=None, when=SEPTEMBER):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=(category or fixtures["category"]).id,
            transaction_date=when,
            amount=amount,
            installment_count=1,
        ),
    )


async def _set_budget(session, category, amount_minor):
    category.monthly_budget_minor = amount_minor
    await session.commit()


async def test_categories_without_a_target_are_left_out(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500")

    assert await budgets.monthly_status(async_session, year=2026, month=9) == []


async def test_status_reports_spent_remaining_and_ratio(
    async_session, people, fixtures
):
    await _set_budget(async_session, fixtures["category"], 400_000)
    await _spend(async_session, people["aykut"], fixtures, "3.200")

    status = (await budgets.monthly_status(async_session, year=2026, month=9))[0]

    assert status.spent_minor == 320_000
    assert status.remaining_minor == 80_000
    assert status.ratio == 80
    assert status.is_exceeded is False
    assert status.bar == "▓▓▓▓▓▓▓▓░░"


async def test_spending_in_another_month_does_not_count(
    async_session, people, fixtures
):
    await _set_budget(async_session, fixtures["category"], 400_000)
    await _spend(
        async_session, people["aykut"], fixtures, "3.200", when=date(2026, 8, 20)
    )

    status = (await budgets.monthly_status(async_session, year=2026, month=9))[0]
    assert status.spent_minor == 0
    assert status.ratio == 0


async def test_exceeding_the_target_is_reported_but_never_blocks_recording(
    async_session, people, fixtures
):
    await _set_budget(async_session, fixtures["category"], 400_000)
    await _spend(async_session, people["aykut"], fixtures, "5.000")

    status = (await budgets.monthly_status(async_session, year=2026, month=9))[0]

    assert status.is_exceeded is True
    assert status.overspend_minor == 100_000
    assert status.remaining_minor == 0


async def test_the_most_strained_category_comes_first(
    async_session, people, fixtures
):
    await _set_budget(async_session, fixtures["category"], 400_000)
    await _set_budget(async_session, fixtures["fuel"], 400_000)
    await _spend(async_session, people["aykut"], fixtures, "100")
    await _spend(
        async_session, people["aykut"], fixtures, "3.900", category=fixtures["fuel"]
    )

    statuses = await budgets.monthly_status(async_session, year=2026, month=9)

    assert [status.name for status in statuses] == ["Yakıt", "Market"]


# ---------------------------------------------------------------------------
# Uyarılar
# ---------------------------------------------------------------------------


async def test_no_alert_below_the_warning_threshold(async_session, people, fixtures):
    await _set_budget(async_session, fixtures["category"], 400_000)
    await _spend(async_session, people["aykut"], fixtures, "2.000")

    statuses = await budgets.monthly_status(async_session, year=2026, month=9)
    assert budgets.alerts_for(statuses) == []


async def test_warning_and_exceeded_are_separate_announcements(
    async_session, people, fixtures
):
    """Aynı kategori ay içinde en fazla iki kez haber verir."""
    await _set_budget(async_session, fixtures["category"], 400_000)
    await _spend(async_session, people["aykut"], fixtures, "3.300")
    bot_first = await budgets.monthly_status(async_session, year=2026, month=9)
    warning = budgets.alerts_for(bot_first)

    await _spend(async_session, people["aykut"], fixtures, "1.000")
    exceeded = budgets.alerts_for(
        await budgets.monthly_status(async_session, year=2026, month=9)
    )

    assert [alert.threshold for alert in warning] == [budgets.WARNING_RATIO]
    assert [alert.threshold for alert in exceeded] == [budgets.EXCEEDED_RATIO]
    assert warning[0].key != exceeded[0].key


# ---------------------------------------------------------------------------
# Gönderim
# ---------------------------------------------------------------------------


async def test_a_budget_alert_is_announced_once_a_month(
    async_session, people, fixtures
):
    from tests.integration.test_reminders import _factory, _settings, sent_notifications

    await _set_budget(async_session, fixtures["category"], 400_000)
    await _spend(async_session, people["aykut"], fixtures, "5.000")

    # Salı ve çarşamba seçilir: pazartesi haftalık, ayın 1'i aylık özet günüdür
    # ve sayım bütçe uyarısıyla karışırdı.
    await scheduler.run_daily_jobs(
        _settings(), _factory(async_session), now=datetime(2026, 9, 8, 9, 0)
    )
    await scheduler.run_daily_jobs(
        _settings(), _factory(async_session), now=datetime(2026, 9, 9, 9, 0)
    )

    sent = await sent_notifications(async_session)
    alerts = [text for _, text in sent if "Bütçe aşıldı" in text]
    assert len(alerts) == 2  # iki kullanici, tek uyari
    assert "Market" in alerts[0]
