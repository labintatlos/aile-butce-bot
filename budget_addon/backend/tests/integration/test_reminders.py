"""Hatırlatmaların üretilmesi ve gönderilmesi.

Zaman hiçbir testte gerçek saatten okunmaz: `today` ve `now` dışarıdan verilir,
böylece ekstre kesim günü veya son ödeme günü beklenmeden sınanabilir.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.bot import scheduler
from app.models import NotificationLog
from app.services import reminders
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

# Kart: hesap kesim 10, son odeme +10 gun. 2026-09-20 pazar oldugu icin son
# odeme pazartesiye tasinir.
STATEMENT_DATE = date(2026, 9, 10)
DUE_DATE = date(2026, 9, 21)


async def _add(session, user, fixtures, *, amount="1.200", count=1, when=date(2026, 9, 5)):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=when,
            amount=amount,
            installment_count=count,
        ),
    )


# ---------------------------------------------------------------------------
# Hangi hatırlatma hangi gün
# ---------------------------------------------------------------------------


async def test_statement_cut_is_announced_on_the_cut_day(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)

    notices = await reminders.card_notices(async_session, today=STATEMENT_DATE)

    kinds = [notice.kind for notice in notices]
    assert reminders.KIND_STATEMENT_CUT in kinds
    cut = next(n for n in notices if n.kind == reminders.KIND_STATEMENT_CUT)
    assert cut.total_minor == 120_000
    assert cut.due_date == DUE_DATE


async def test_due_warning_arrives_the_configured_number_of_days_early(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)

    three_days_before = DUE_DATE - timedelta(days=3)
    notices = await reminders.card_notices(
        async_session, today=three_days_before, due_reminder_days=3
    )

    warning = next(n for n in notices if n.kind == reminders.KIND_DUE_SOON)
    assert warning.days_until_due == 3
    assert warning.total_minor == 120_000


async def test_no_warning_on_other_days(async_session, people, fixtures):
    await _add(async_session, people["aykut"], fixtures)

    quiet_day = DUE_DATE - timedelta(days=5)
    notices = await reminders.card_notices(
        async_session, today=quiet_day, due_reminder_days=3
    )

    assert notices == []


async def test_due_today_is_announced_even_though_the_cut_day_has_passed(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)

    notices = await reminders.card_notices(async_session, today=DUE_DATE)

    assert [n.kind for n in notices] == [reminders.KIND_DUE_TODAY]


async def test_cash_expenses_never_produce_card_reminders(
    async_session, people, fixtures
):
    await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 5),
            amount="500",
            installment_count=1,
        ),
    )

    for day in (STATEMENT_DATE, DUE_DATE):
        assert await reminders.card_notices(async_session, today=day) == []


# ---------------------------------------------------------------------------
# Dönem özetleri
# ---------------------------------------------------------------------------


async def test_period_summary_sums_only_the_given_range(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures, amount="100", when=date(2026, 9, 2))
    await _add(async_session, people["aslihan"], fixtures, amount="300", when=date(2026, 9, 4))
    await _add(async_session, people["aykut"], fixtures, amount="999", when=date(2026, 9, 9))

    summary = await reminders.period_summary(
        async_session,
        kind=reminders.KIND_WEEKLY,
        start=date(2026, 8, 31),
        end=date(2026, 9, 6),
    )

    assert summary.total_minor == 40_000
    assert summary.transaction_count == 2
    assert [person.name for person in summary.by_user] == ["Aslıhan", "Aykut"]


async def test_empty_period_produces_no_summary(async_session, people, fixtures):
    summaries = await reminders.period_summaries(async_session, today=date(2026, 9, 7))
    assert summaries == []


# ---------------------------------------------------------------------------
# Gönderim
# ---------------------------------------------------------------------------


class FakeBot:
    """Telegram yerine geçen kayıt tutucu."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def _settings(**overrides):
    from app.config import Settings

    defaults = dict(
        authorized_telegram_ids="111,222",
        reminder_hour=9,
        due_reminder_days=3,
        _env_file=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _factory(async_session):
    """Zamanlayıcı kendi oturumunu açar; testte tek oturum paylaşılır."""

    class _Once:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Once()


async def test_reminder_is_sent_once_and_not_repeated(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)
    bot = FakeBot()
    at_nine = datetime(2026, 9, 10, 9, 0)

    first = await scheduler.deliver_due_reminders(
        bot, _settings(), _factory(async_session), now=at_nine
    )
    second = await scheduler.deliver_due_reminders(
        bot, _settings(), _factory(async_session), now=at_nine.replace(minute=30)
    )

    # Iki kullanici, tek ekstre kesim hatirlatmasi.
    assert first == 2
    assert second == 0
    assert len(bot.sent) == 2
    assert {chat_id for chat_id, _ in bot.sent} == {111, 222}
    assert "ekstre kesiliyor" in bot.sent[0][1]


async def test_nothing_is_sent_outside_the_reminder_hour(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)
    bot = FakeBot()

    sent = await scheduler.deliver_due_reminders(
        bot,
        _settings(),
        _factory(async_session),
        now=datetime(2026, 9, 10, 14, 0),
    )

    assert sent == 0
    assert bot.sent == []
    logged = await async_session.scalar(
        select(func.count()).select_from(NotificationLog)
    )
    assert logged == 0


async def test_user_who_turned_reminders_off_is_skipped(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)
    people["aslihan"].reminders_enabled = False
    await async_session.commit()
    bot = FakeBot()

    sent = await scheduler.deliver_due_reminders(
        bot, _settings(), _factory(async_session), now=datetime(2026, 9, 10, 9, 0)
    )

    assert sent == 1
    assert [chat_id for chat_id, _ in bot.sent] == [111]


async def test_failed_delivery_is_retried_on_the_next_tick(
    async_session, people, fixtures
):
    await _add(async_session, people["aykut"], fixtures)

    class BrokenBot(FakeBot):
        def __init__(self):
            super().__init__()
            self.fail = True

        async def send_message(self, chat_id: int, text: str) -> None:
            if self.fail:
                raise RuntimeError("ağ hatası")
            await super().send_message(chat_id, text)

    bot = BrokenBot()
    at_nine = datetime(2026, 9, 10, 9, 0)

    assert (
        await scheduler.deliver_due_reminders(
            bot, _settings(), _factory(async_session), now=at_nine
        )
        == 0
    )

    bot.fail = False
    assert (
        await scheduler.deliver_due_reminders(
            bot, _settings(), _factory(async_session), now=at_nine
        )
        == 2
    )
