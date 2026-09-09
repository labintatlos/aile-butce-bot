"""Hatırlatma pencerelerinin takvim mantığı.

Dönem özetleri **kapanmış** dönemi anlatmalıdır; yarım hafta veya yarım ay
toplamı bildirim olarak gönderilirse kullanıcı yanlış bir tabloya bakar.
"""

from __future__ import annotations

from datetime import date

from app.services import reminders


def test_previous_week_is_the_closed_monday_to_sunday_window():
    # 2026-09-10 persembe; kapanmis hafta 31 Agustos - 6 Eylul.
    assert reminders.previous_week(date(2026, 9, 10)) == (
        date(2026, 8, 31),
        date(2026, 9, 6),
    )


def test_previous_week_on_a_monday_does_not_include_today():
    assert reminders.previous_week(date(2026, 9, 7)) == (
        date(2026, 8, 31),
        date(2026, 9, 6),
    )


def test_previous_month_crosses_the_year_boundary():
    assert reminders.previous_month(date(2027, 1, 1)) == (
        date(2026, 12, 1),
        date(2026, 12, 31),
    )


def test_weekly_summary_is_due_only_on_monday():
    kinds = [kind for kind, _, _ in reminders.due_period_summaries(date(2026, 9, 7))]
    assert kinds == [reminders.KIND_WEEKLY]

    assert reminders.due_period_summaries(date(2026, 9, 8)) == []


def test_monthly_summary_is_due_on_the_first():
    kinds = [kind for kind, _, _ in reminders.due_period_summaries(date(2026, 9, 1))]
    assert kinds == [reminders.KIND_MONTHLY]


def test_both_summaries_can_fall_on_the_same_day():
    # 2026-06-01 pazartesi: hem haftalik hem aylik ozet gunu.
    kinds = [kind for kind, _, _ in reminders.due_period_summaries(date(2026, 6, 1))]
    assert kinds == [reminders.KIND_WEEKLY, reminders.KIND_MONTHLY]
