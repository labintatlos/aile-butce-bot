"""Takvim testleri. Senaryo kimlikleri: docs/TEST_SCENARIOS.md (U-D*)."""

from datetime import date

import pytest

from app.services.finance.dates import add_months, normalized_date


def test_u_d1_day_31_in_february_falls_back_to_28():
    assert normalized_date(2027, 2, 31) == date(2027, 2, 28)


def test_u_d2_day_31_in_leap_february_falls_back_to_29():
    assert normalized_date(2028, 2, 31) == date(2028, 2, 29)


def test_u_d3_day_30_in_february_falls_back_to_month_end():
    assert normalized_date(2027, 2, 30) == date(2027, 2, 28)


def test_u_d4_preferred_day_is_restored_after_a_short_month():
    # Subat'ta 28'e inen bir gun, Mart'ta tekrar 31 olmalidir.
    assert add_months(date(2027, 2, 28), 1, preferred_day=31) == date(2027, 3, 31)


def test_u_d5_year_rolls_over_from_december_to_january():
    assert add_months(date(2026, 12, 10), 1, preferred_day=10) == date(2027, 1, 10)


def test_u_d5b_twelve_months_lands_on_the_next_year():
    assert add_months(date(2026, 9, 10), 12, preferred_day=10) == date(2027, 9, 10)


@pytest.mark.parametrize("day", [0, 32, -1])
def test_u_d6_day_out_of_range_is_rejected(day):
    with pytest.raises(ValueError):
        normalized_date(2026, 9, day)


def test_add_months_without_preferred_day_keeps_source_day():
    assert add_months(date(2026, 9, 8), 2) == date(2026, 11, 8)
