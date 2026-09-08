"""Ekstre ve son ödeme tarihi testleri. Kimlikler: docs/TEST_SCENARIOS.md (U-S*)."""

from datetime import date

import pytest

from app.services.finance.statement import due_date_for, first_statement_date

STATEMENT_DAY = 10


def test_u_s1_transaction_before_cutoff_hits_the_same_month():
    assert first_statement_date(date(2026, 9, 8), STATEMENT_DAY) == date(2026, 9, 10)


def test_u_s2_transaction_on_cutoff_day_inclusive_hits_the_same_month():
    assert first_statement_date(
        date(2026, 9, 10), STATEMENT_DAY, cutoff_inclusive=True
    ) == date(2026, 9, 10)


def test_u_s3_transaction_on_cutoff_day_exclusive_moves_to_next_month():
    assert first_statement_date(
        date(2026, 9, 10), STATEMENT_DAY, cutoff_inclusive=False
    ) == date(2026, 10, 10)


def test_u_s4_transaction_after_cutoff_moves_to_next_month():
    assert first_statement_date(date(2026, 9, 11), STATEMENT_DAY) == date(2026, 10, 10)


def test_u_s5_transaction_after_december_cutoff_moves_into_next_year():
    assert first_statement_date(date(2026, 12, 15), STATEMENT_DAY) == date(2027, 1, 10)


def test_u_s5b_cutoff_day_missing_from_february_is_normalised():
    # statement_day 31, Subat 2027 -> 28 Subat ekstresi
    assert first_statement_date(date(2027, 2, 20), 31) == date(2027, 2, 28)


def test_u_s6_due_day_after_statement_day_stays_in_the_same_month():
    assert due_date_for(date(2026, 9, 10), STATEMENT_DAY, 20) == date(2026, 9, 20)


def test_u_s7_due_day_before_statement_day_moves_to_next_month():
    assert due_date_for(date(2026, 9, 28), 28, 8) == date(2026, 10, 8)


def test_u_s8_due_day_equal_to_statement_day_moves_to_next_month():
    assert due_date_for(date(2026, 9, 10), STATEMENT_DAY, 10) == date(2026, 10, 10)


def test_u_s9_december_statement_is_paid_in_january():
    assert due_date_for(date(2026, 12, 25), 25, 5) == date(2027, 1, 5)


def test_u_s10_month_offset_uses_configured_days_not_normalised_ones():
    # statement_day 31 Subat'ta 28'e iner; due_day 10 <= 31 oldugu icin
    # karar yine takip eden ay yonunde verilmelidir.
    assert due_date_for(date(2027, 2, 28), 31, 10) == date(2027, 3, 10)


@pytest.mark.parametrize("day", [0, 32])
def test_invalid_days_are_rejected(day):
    with pytest.raises(ValueError):
        first_statement_date(date(2026, 9, 8), day)
    with pytest.raises(ValueError):
        due_date_for(date(2026, 9, 10), STATEMENT_DAY, day)
