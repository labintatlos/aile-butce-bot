"""Yeni özelliklerin saf kuralları: orantılı dağıtım, ekstre okuma, kural
eşleştirme ve hesap bakiyesi."""

from __future__ import annotations

from datetime import date

import pytest

from app.models.account import ENTRY_ADJUSTMENT, ENTRY_BALANCE, ENTRY_TRANSFER, AccountEntry
from app.models.rule import MATCH_CONTAINS, MATCH_EQUALS, MATCH_STARTS_WITH, Rule
from app.services import importer
from app.services.accounts import balance_at
from app.services.finance.money import allocate_proportionally
from app.services.rules import evaluate, keep_tags, matches

# ---------------------------------------------------------------------------
# Orantili dagitim
# ---------------------------------------------------------------------------


def test_allocation_never_loses_a_kurus():
    assert allocate_proportionally(100, [1, 1, 1]) == [34, 33, 33]
    assert sum(allocate_proportionally(1_001, [900, 300])) == 1_001


def test_allocation_follows_the_weights():
    # 1.200 TL'lik fisin 900'u gida, 300'u temizlik; 400 TL iade 3'e 1 bolunur.
    assert allocate_proportionally(40_000, [90_000, 30_000]) == [30_000, 10_000]


def test_allocation_gives_leftover_kurus_to_the_largest_remainder():
    assert allocate_proportionally(10, [1, 2]) == [3, 7]


@pytest.mark.parametrize("weights", [[], [0, 0], [-1, 2]])
def test_allocation_rejects_meaningless_weights(weights):
    with pytest.raises(ValueError):
        allocate_proportionally(100, weights)


# ---------------------------------------------------------------------------
# Ekstre hucreleri
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("12.10.2026", date(2026, 10, 12)),
        ("12/10/26", date(2026, 10, 12)),
        ("2026-10-12", date(2026, 10, 12)),
        ("12.10.2026 14:33", date(2026, 10, 12)),
        ("31.02.2026", None),
        ("Migros", None),
        ("", None),
    ],
)
def test_statement_dates_are_read_day_first(cell, expected):
    assert importer.parse_date(cell) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1.234,56", 123_456),
        ("-1.234,56", -123_456),
        ("1,234.56", 123_456),
        ("1234.56-", -123_456),
        ("(250,00)", -25_000),
        ("+1.234,56 TL", 123_456),
        ("1.250", 125_000),
        ("12,5", 1_250),
        ("abc", None),
        ("", None),
    ],
)
def test_statement_amounts_keep_their_sign(cell, expected):
    assert importer.parse_signed_amount(cell) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("TEKNOSA 2/6 TAKSIT", (2, 6)),
        ("Vatan 1 / 3", (1, 3)),
        ("MIGROS 1234", None),
        ("Ödeme 0/3", None),
        ("Hatalı 5/3", None),
        ("1/1", None),
    ],
)
def test_installment_lines_are_recognised(text, expected):
    assert importer.installment_hint(text) == expected


BANK_EXPORT = """Hesap Ekstresi;;;
Kart No;5555 **** **** 1234;;
;;;
İşlem Tarihi;Açıklama;Tutar;Bonus
01.10.2026;MIGROS ISTANBUL;1.250,40;12,50
03.10.2026;SHELL BENZIN;2.000,00;0
05.10.2026;ODEME - TESEKKURLER;-5.000,00;0
"""


def test_columns_and_the_first_row_are_found_from_the_header():
    rows, delimiter = importer.read_table(BANK_EXPORT)
    mapping = importer.guess_mapping(rows)

    assert delimiter == ";"
    assert mapping == importer.ColumnMapping(
        date_column=0, description_column=1, amount_column=2, first_row=4
    )


def test_columns_are_guessed_from_content_when_there_is_no_header():
    rows, _ = importer.read_table(
        "2026-10-01,1234567890123,Market alisverisi,-150.25\n"
        "2026-10-02,1234567890124,Eczane,-80.00\n"
    )
    mapping = importer.guess_mapping(rows)

    assert (mapping.date_column, mapping.description_column, mapping.amount_column) == (0, 2, 3)


def test_a_file_without_dates_is_refused():
    rows, _ = importer.read_table("a;b\nc;d\n")
    with pytest.raises(importer.ImportFileError):
        importer.guess_mapping(rows)


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


def _rule(rule_id, pattern, match_type=MATCH_CONTAINS, **actions) -> Rule:
    return Rule(id=rule_id, pattern=pattern, match_type=match_type, is_active=True, **actions)


def test_matching_ignores_case_turkish_letters_and_tags():
    rule = _rule(1, "migros")
    assert matches(rule, "MİGROS Kadıköy #tatil")
    assert not matches(_rule(2, "migros", MATCH_EQUALS), "Migros Kadıköy")
    assert matches(_rule(3, "migros", MATCH_EQUALS), "MIGROS #tatil")
    assert matches(_rule(4, "shell", MATCH_STARTS_WITH), "Shell Benzin")
    assert not matches(_rule(5, "benzin", MATCH_STARTS_WITH), "Shell Benzin")


def test_the_first_rule_to_fill_a_field_wins():
    rules = [
        _rule(1, "migros sanal", set_category_id=7),
        _rule(2, "migros", set_category_id=3, set_description="Migros"),
    ]
    outcome = evaluate(rules, "MIGROS SANAL MARKET #ev")

    assert outcome.category_id == 7
    assert outcome.description == "Migros #ev"
    assert outcome.rule_ids == (1, 2)


def test_inactive_rules_are_skipped():
    rule = _rule(1, "migros", set_category_id=3)
    rule.is_active = False
    assert not evaluate([rule], "migros").matched


def test_renaming_keeps_tags():
    assert keep_tags("MIGROS 1234 #tatil #kisisel", "Migros") == "Migros #tatil #kisisel"
    assert keep_tags(None, "Migros") == "Migros"


# ---------------------------------------------------------------------------
# Hesap bakiyesi
# ---------------------------------------------------------------------------


def _entry(entry_id, when, kind, amount) -> AccountEntry:
    return AccountEntry(id=entry_id, account_id=1, entry_date=when, kind=kind, amount_minor=amount)


def test_balance_starts_from_the_last_snapshot_and_adds_later_movements():
    entries = [
        _entry(1, date(2026, 9, 1), ENTRY_BALANCE, 1_000_00),
        _entry(2, date(2026, 9, 10), ENTRY_TRANSFER, -200_00),
        _entry(3, date(2026, 10, 1), ENTRY_BALANCE, 5_000_00),
        _entry(4, date(2026, 10, 5), ENTRY_ADJUSTMENT, 25_00),
    ]
    assert balance_at(entries, date(2026, 8, 31)) == 0
    assert balance_at(entries, date(2026, 9, 15)) == 800_00
    assert balance_at(entries, date(2026, 10, 1)) == 5_000_00
    assert balance_at(entries, date(2026, 10, 31)) == 5_025_00


def test_a_back_dated_snapshot_does_not_erase_later_transfers():
    entries = [
        _entry(1, date(2026, 10, 10), ENTRY_TRANSFER, 300_00),
        # Sonradan girilmis ama 1 Ekim tarihli bakiye.
        _entry(2, date(2026, 10, 1), ENTRY_BALANCE, 1_000_00),
    ]
    assert balance_at(entries, date(2026, 10, 15)) == 1_300_00
