"""Ekstre ve son ödeme tarihi testleri. Kimlikler: docs/TEST_SCENARIOS.md (U-S*).

Kullanıcı yalnızca hesap kesim gününü girer. Son ödeme tarihi ekstreden
`due_offset_days` gün sonrasıdır ve hafta sonuna denk gelirse pazartesiye
taşınır.
"""

from datetime import date

import pytest

from app.services.finance.statement import (
    DEFAULT_DUE_OFFSET_DAYS,
    due_date_for,
    first_statement_date,
)

STATEMENT_DAY = 10


# ---------------------------------------------------------------------------
# Ilk ekstre tarihi (degismedi)
# ---------------------------------------------------------------------------


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
    assert first_statement_date(date(2027, 2, 20), 31) == date(2027, 2, 28)


@pytest.mark.parametrize("day", [0, 32])
def test_invalid_statement_days_are_rejected(day):
    with pytest.raises(ValueError):
        first_statement_date(date(2026, 9, 8), day)


# ---------------------------------------------------------------------------
# Son odeme tarihi: kesimden N gun sonra
# ---------------------------------------------------------------------------


def test_u_s6_due_date_is_the_offset_after_the_statement():
    # 10 Eylul 2026 persembe; +10 gun = 20 Eylul, pazar -> 21 Eylul pazartesi
    assert due_date_for(date(2026, 10, 10), 10) == date(2026, 10, 20)


def test_u_s7_due_date_crosses_into_the_next_month():
    assert due_date_for(date(2026, 9, 28), 10) == date(2026, 10, 8)


def test_u_s8_due_date_crosses_into_the_next_year():
    assert due_date_for(date(2026, 12, 28), 10) == date(2027, 1, 7)


def test_u_s9_month_length_never_produces_an_impossible_date():
    """Gün ekleme takvimi doğrudan takip eder; 31 Ocak + 10 gün sorun değil."""
    assert due_date_for(date(2027, 1, 31), 10) == date(2027, 2, 10)
    assert due_date_for(date(2028, 2, 29), 10) == date(2028, 3, 10)


def test_default_offset_is_used_when_not_given():
    assert due_date_for(date(2026, 10, 10)) == due_date_for(
        date(2026, 10, 10), DEFAULT_DUE_OFFSET_DAYS
    )


@pytest.mark.parametrize("offset", [0, 61, -1])
def test_an_out_of_range_offset_is_rejected(offset):
    with pytest.raises(ValueError):
        due_date_for(date(2026, 9, 10), offset)


# ---------------------------------------------------------------------------
# Hafta sonu kaydirmasi
# ---------------------------------------------------------------------------


def test_u_s10_a_saturday_due_date_moves_to_monday():
    # 12 Eylul 2026 cumartesi
    assert due_date_for(date(2026, 9, 2), 10) == date(2026, 9, 14)


def test_u_s11_a_sunday_due_date_moves_to_monday():
    # 10 Eylul + 10 = 20 Eylul 2026, pazar
    assert due_date_for(date(2026, 9, 10), 10) == date(2026, 9, 21)


def test_u_s12_a_weekday_due_date_is_left_alone():
    result = due_date_for(date(2026, 10, 10), 10)
    assert result == date(2026, 10, 20)
    assert result.weekday() < 5


@pytest.mark.parametrize("statement", [date(2026, m, 10) for m in range(1, 13)])
def test_no_due_date_ever_falls_on_a_weekend(statement):
    """Bankalar hafta sonu tahsilat yapmaz; hiçbir son ödeme oraya düşmemeli."""
    assert due_date_for(statement, 10).weekday() < 5


# ---------------------------------------------------------------------------
# Resmi tatil kaydirmasi
# ---------------------------------------------------------------------------


def test_a_national_holiday_moves_to_the_next_business_day():
    # 19 Ekim + 10 = 29 Ekim 2026 persembe, Cumhuriyet Bayrami -> 30 Ekim cuma
    assert due_date_for(date(2026, 10, 19), 10) == date(2026, 10, 30)


def test_a_religious_holiday_moves_to_the_next_business_day():
    # 10 Mart + 10 = 20 Mart 2026 cuma, Ramazan Bayrami -> 23 Mart pazartesi
    assert due_date_for(date(2026, 3, 10), 10) == date(2026, 3, 23)


def test_a_holiday_running_into_the_weekend_skips_both():
    # 27-30 Mayis 2026 Kurban Bayrami, 31 Mayis pazar -> 1 Haziran pazartesi
    assert due_date_for(date(2026, 5, 17), 10) == date(2026, 6, 1)


def test_the_half_day_eve_counts_as_a_business_day():
    # 26 Mayis 2026 Kurban Bayrami arifesi; bankalar ogleye kadar acik
    assert due_date_for(date(2026, 5, 16), 10) == date(2026, 5, 26)


def test_shifting_never_moves_the_due_date_earlier():
    for day in range(1, 29):
        statement = date(2026, 9, day)
        assert due_date_for(statement, 10) >= statement
