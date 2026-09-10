"""Kart limiti ve kullanılabilir bakiye.

Buradaki ayrım önemlidir: 12 taksitli bir alışverişin **tamamı** limitten
düşer, ekstreye ise ayda bir taksiti gelir. Limit takibi ekstre takibinden
farklı bir soruyu yanıtlar.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services import scheduler
from app.models.installment import STATUS_PAID
from app.services import cards
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

SEPTEMBER = date(2026, 9, 5)


async def _spend(session, user, fixtures, amount, *, count=1, card="card"):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures[card].id,
            category_id=fixtures["category"].id,
            transaction_date=SEPTEMBER,
            amount=amount,
            installment_count=count,
        ),
    )


async def _set_limit(session, card, limit_minor):
    card.credit_limit_minor = limit_minor
    await session.commit()


def _find(usages, name):
    return next(usage for usage in usages if usage.name == name)


async def test_a_card_without_a_limit_reports_debt_but_no_ratio(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "1.000")

    usage = _find(await cards.card_usage(async_session), fixtures["card"].name)

    assert usage.outstanding_minor == 100_000
    assert usage.has_limit is False
    assert usage.ratio == 0
    assert usage.available_minor == 0


async def test_the_whole_instalment_plan_is_committed_to_the_limit(
    async_session, people, fixtures
):
    """Ekstreye bir taksit gelir ama limitten alışverişin tamamı düşer."""
    await _set_limit(async_session, fixtures["card"], 5_000_000)
    await _spend(async_session, people["aykut"], fixtures, "12.000", count=12)

    usage = _find(await cards.card_usage(async_session), fixtures["card"].name)

    assert usage.outstanding_minor == 1_200_000
    assert usage.available_minor == 3_800_000
    assert usage.ratio == 24


async def test_a_paid_instalment_frees_the_limit(async_session, people, fixtures):
    await _set_limit(async_session, fixtures["card"], 1_000_000)
    expense = await _spend(async_session, people["aykut"], fixtures, "1.200", count=12)

    expense.installments[0].status = STATUS_PAID
    await async_session.commit()

    usage = _find(await cards.card_usage(async_session), fixtures["card"].name)
    assert usage.outstanding_minor == 110_000


async def test_cash_spending_never_touches_a_card_limit(
    async_session, people, fixtures
):
    await _set_limit(async_session, fixtures["card"], 1_000_000)
    await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=SEPTEMBER,
            amount="500",
            installment_count=1,
        ),
    )

    usage = _find(await cards.card_usage(async_session), fixtures["card"].name)
    assert usage.outstanding_minor == 0


async def test_going_over_the_limit_is_reported_without_a_negative_balance(
    async_session, people, fixtures
):
    await _set_limit(async_session, fixtures["card"], 100_000)
    await _spend(async_session, people["aykut"], fixtures, "1.500")

    usage = _find(await cards.card_usage(async_session), fixtures["card"].name)

    assert usage.is_over_limit is True
    assert usage.available_minor == 0
    assert usage.ratio == 150


async def test_the_fullest_card_comes_first(async_session, people, fixtures):
    await _set_limit(async_session, fixtures["card"], 1_000_000)
    await _set_limit(async_session, fixtures["other_card"], 1_000_000)
    await _spend(async_session, people["aykut"], fixtures, "100")
    await _spend(async_session, people["aykut"], fixtures, "9.000", card="other_card")

    usages = await cards.card_usage(async_session)

    assert [usage.name for usage in usages] == [
        fixtures["other_card"].name,
        fixtures["card"].name,
    ]


# ---------------------------------------------------------------------------
# Uyarılar
# ---------------------------------------------------------------------------


async def test_no_alert_for_a_card_without_a_limit(async_session, people, fixtures):
    await _spend(async_session, people["aykut"], fixtures, "50.000")

    usages = await cards.card_usage(async_session)
    assert cards.alerts_for(usages, year=2026, month=9) == []


async def test_alert_when_nine_tenths_of_the_limit_is_committed(
    async_session, people, fixtures
):
    await _set_limit(async_session, fixtures["card"], 1_000_000)
    await _spend(async_session, people["aykut"], fixtures, "9.200")

    alerts = cards.alerts_for(await cards.card_usage(async_session), year=2026, month=9)

    assert [alert.threshold for alert in alerts] == [cards.NEAR_LIMIT_RATIO]


async def test_a_card_limit_alert_is_announced_once_a_month(
    async_session, people, fixtures
):
    from tests.integration.test_reminders import _factory, _settings, sent_notifications

    await _set_limit(async_session, fixtures["card"], 100_000)
    await _spend(async_session, people["aykut"], fixtures, "1.500")

    await scheduler.run_daily_jobs(
        _settings(), _factory(async_session), now=datetime(2026, 9, 8, 9, 0)
    )
    await scheduler.run_daily_jobs(
        _settings(), _factory(async_session), now=datetime(2026, 9, 9, 9, 0)
    )

    sent = await sent_notifications(async_session)
    alerts = [text for _, text in sent if "Kart limiti aşıldı" in text]
    assert len(alerts) == 2  # iki kullanici, tek uyari
