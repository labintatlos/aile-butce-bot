"""Para aritmetiği testleri. Senaryo kimlikleri: docs/TEST_SCENARIOS.md (U-M*)."""

from decimal import Decimal

import pytest

from app.services.finance.money import (
    MAX_INSTALLMENTS,
    format_try,
    parse_amount_to_minor,
    split_minor,
)


def test_u_m1_thousand_lira_over_three_installments_loses_no_kurus():
    amounts = split_minor(100_000, 3)
    assert amounts == [33_334, 33_333, 33_333]
    assert sum(amounts) == 100_000


def test_u_m2_single_kurus_single_installment():
    assert split_minor(1, 1) == [1]


@pytest.mark.parametrize("count", range(1, MAX_INSTALLMENTS + 1))
def test_u_m3_split_always_preserves_total(count):
    for total_minor in range(1, 500):
        amounts = split_minor(total_minor, count)
        assert sum(amounts) == total_minor
        assert len(amounts) == count
        assert max(amounts) - min(amounts) <= 1


@pytest.mark.parametrize(
    "raw",
    ["1.250,50", "1250,50", "1250.50", "₺1.250,50", "1.250,50 TL", Decimal("1250.50")],
)
def test_u_m4_accepted_input_formats(raw):
    assert parse_amount_to_minor(raw) == 125_050


def test_u_m4b_ambiguous_single_dot_is_resolved_by_group_size():
    assert parse_amount_to_minor("1.250") == 125_000  # binlik ayraci
    assert parse_amount_to_minor("10.50") == 1_050  # ondalik ayraci


@pytest.mark.parametrize("raw", ["0", "-5", "", "   ", "abc", "1,2,3"])
def test_u_m5_invalid_input_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_amount_to_minor(raw)


def test_u_m6_rounds_half_up():
    assert parse_amount_to_minor("10,005") == 1_001


def test_u_m7_turkish_currency_formatting():
    assert format_try(1_245_075) == "12.450,75 TL"
    assert format_try(50) == "0,50 TL"
    assert format_try(100) == "1,00 TL"


@pytest.mark.parametrize("count", [0, -1, MAX_INSTALLMENTS + 1])
def test_u_m8_installment_count_out_of_range(count):
    with pytest.raises(ValueError):
        split_minor(100_000, count)


def test_u_m9_booleans_are_not_amounts():
    with pytest.raises(ValueError):
        parse_amount_to_minor(True)
