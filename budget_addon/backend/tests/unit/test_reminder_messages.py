"""Hatırlatma ve sabit gider mesajlarının metni.

Mesajlar saf fonksiyonlardır; biçim bozulursa kullanıcı bunu ancak gerçek bir
bildirimde görürdü.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.bot import messages
from app.services import reminders


def _notice(kind, **overrides):
    defaults = dict(
        kind=kind,
        payment_method_id=1,
        payment_method_name="Aykut Kredi Kartı 1",
        statement_date=date(2026, 9, 10),
        due_date=date(2026, 9, 21),
        total_minor=1_248_000,
        installment_count=5,
        days_until_due=3,
    )
    defaults.update(overrides)
    return reminders.CardNotice(**defaults)


def test_statement_cut_message_names_the_card_and_the_due_date():
    text = messages.card_notice(_notice(reminders.KIND_STATEMENT_CUT))
    assert "ekstre kesiliyor" in text
    assert "Aykut Kredi Kartı 1" in text
    assert "12.480,00" in text
    assert "21 Eylül 2026" in text


def test_due_soon_message_counts_the_remaining_days():
    text = messages.card_notice(_notice(reminders.KIND_DUE_SOON))
    assert "3 gün kaldı" in text


def test_due_today_message_says_today():
    text = messages.card_notice(_notice(reminders.KIND_DUE_TODAY, days_until_due=0))
    assert "bugün" in text


def test_weekly_summary_lists_people_and_categories():
    summary = reminders.PeriodSummary(
        kind=reminders.KIND_WEEKLY,
        start=date(2026, 8, 31),
        end=date(2026, 9, 6),
        total_minor=250_000,
        transaction_count=7,
        by_user=[reminders.reports.NamedTotal(id=1, name="Aykut", total_minor=250_000)],
        by_category=[
            reminders.reports.NamedTotal(
                id=1, name="Market", total_minor=250_000, emoji="🛒"
            )
        ],
    )

    text = messages.period_summary(summary)

    assert "Geçen hafta" in text
    assert "Aykut" in text
    assert "🛒 Market" in text


def test_empty_recurring_list_explains_what_the_feature_is_for():
    assert "Kira" in messages.recurring_list([], categories={}, methods={})


def test_recurring_list_shows_the_monthly_total():
    template = SimpleNamespace(
        id=3,
        name="Kira",
        amount_minor=1_500_000,
        day_of_month=1,
        category_id=1,
        payment_method_id=2,
        is_active=True,
    )
    categories = {1: SimpleNamespace(name="Kira", emoji="🏠")}
    methods = {2: SimpleNamespace(name="Nakit")}

    text = messages.recurring_list([template], categories=categories, methods=methods)

    assert "15.000,00" in text
    assert "Aylık toplam" in text
