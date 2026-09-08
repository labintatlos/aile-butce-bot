"""Taksit planı testleri. Kimlikler: docs/TEST_SCENARIOS.md (U-I*)."""

from datetime import date

import pytest

from app.services.finance.installments import build_schedule

CARD = {"statement_day": 10}


def build(total_minor, count, transaction_date, **overrides):
    options = {**CARD, **overrides}
    return build_schedule(
        total_minor=total_minor,
        installment_count=count,
        transaction_date=transaction_date,
        **options,
    )


def test_u_i1_twelve_installments_advance_one_month_at_a_time():
    schedule = build(1_200_000, 12, date(2026, 9, 8))
    assert len(schedule) == 12
    assert schedule[0].statement_date == date(2026, 9, 10)
    assert schedule[-1].statement_date == date(2027, 8, 10)
    assert schedule[-1].due_date == date(2027, 8, 20)


def test_u_i2_single_installment_has_one_line():
    schedule = build(50_000, 1, date(2026, 9, 8))
    assert len(schedule) == 1
    assert schedule[0].amount_minor == 50_000
    assert schedule[0].statement_date == date(2026, 9, 10)


def test_u_i3_cash_cannot_be_paid_in_installments():
    with pytest.raises(ValueError):
        build_schedule(
            total_minor=50_000,
            installment_count=3,
            transaction_date=date(2026, 9, 8),
            statement_day=None,
        )


def test_u_i4_cash_schedule_uses_the_transaction_date():
    schedule = build_schedule(
        total_minor=50_000,
        installment_count=1,
        transaction_date=date(2026, 9, 8),
        statement_day=None,
    )
    assert len(schedule) == 1
    assert schedule[0].statement_date == date(2026, 9, 8)
    assert schedule[0].due_date == date(2026, 9, 8)


@pytest.mark.parametrize("count", range(1, 13))
@pytest.mark.parametrize("total_minor", [1, 7, 100_001, 1_234_567])
def test_u_i5_schedule_total_always_matches_the_expense_total(count, total_minor):
    schedule = build(total_minor, count, date(2026, 9, 8))
    assert sum(line.amount_minor for line in schedule) == total_minor


def test_u_i6_statement_dates_are_strictly_increasing():
    schedule = build(1_200_000, 12, date(2026, 1, 31), statement_day=31)
    statements = [line.statement_date for line in schedule]
    assert statements == sorted(statements)
    assert len(set(statements)) == len(statements)


def test_u_i7_due_date_is_never_before_its_statement_date():
    schedule = build(600_000, 6, date(2026, 9, 8), statement_day=28)
    assert all(line.due_date >= line.statement_date for line in schedule)


def test_u_i8_a_card_needs_only_a_statement_day():
    """Son ödeme günü artık girilmez; ekstre tarihinden türetilir."""
    schedule = build_schedule(
        total_minor=50_000,
        installment_count=1,
        transaction_date=date(2026, 9, 8),
        statement_day=10,
    )
    assert schedule[0].statement_date == date(2026, 9, 10)
    # 20 Eylul 2026 pazar oldugu icin 21 Eylul pazartesiye tasinir.
    assert schedule[0].due_date == date(2026, 9, 21)


def test_an_out_of_range_due_offset_is_rejected():
    with pytest.raises(ValueError):
        build_schedule(
            total_minor=50_000,
            installment_count=1,
            transaction_date=date(2026, 9, 8),
            statement_day=10,
            due_offset_days=0,
        )
