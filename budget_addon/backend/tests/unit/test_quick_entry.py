"""Hızlı metin girişi testleri. Kimlikler: docs/TEST_SCENARIOS.md (U-Q*)."""

from __future__ import annotations

import pytest

from app.models.category import Category
from app.services.quick_entry import NotAnExpense, fold, parse_quick_entry


def category(name: str, active: bool = True) -> Category:
    return Category(name=name, emoji="", is_active=active)


@pytest.fixture()
def categories():
    return [
        category("Market"),
        category("Yeme & İçme"),
        category("Yakıt"),
        category("Giyim"),
        category("Sağlık"),
        category("Eğlence", active=False),
    ]


def test_u_q1_amount_and_category(categories):
    entry = parse_quick_entry("500 market", categories)
    assert entry.amount_minor == 50_000
    assert entry.category.name == "Market"
    assert entry.description is None


def test_u_q2_amount_category_and_description(categories):
    entry = parse_quick_entry("1.250,50 market Migros alışverişi", categories)
    assert entry.amount_minor == 125_050
    assert entry.category.name == "Market"
    assert entry.description == "Migros alışverişi"


def test_u_q3_amount_only_asks_for_a_category(categories):
    entry = parse_quick_entry("320", categories)
    assert entry.amount_minor == 32_000
    assert entry.needs_category_choice
    assert entry.candidates


@pytest.mark.parametrize("text", ["merhaba", "", "   ", "market 500"])
def test_u_q4_text_without_a_leading_amount_is_not_an_expense(text, categories):
    with pytest.raises(NotAnExpense):
        parse_quick_entry(text, categories)


def test_u_q5_unique_prefix_matches(categories):
    entry = parse_quick_entry("100 ye", categories)
    assert entry.category.name == "Yeme & İçme"


def test_u_q6_ambiguous_prefix_asks_instead_of_guessing(categories):
    # "Yakit" ve "Yeme & Icme" ayni harfle baslar; "y" tek basina belirsizdir.
    entry = parse_quick_entry("100 y", categories)
    assert entry.needs_category_choice
    assert {c.name for c in entry.candidates} == {"Yeme & İçme", "Yakıt"}


@pytest.mark.parametrize("token", ["MARKET", "mArKeT", "market"])
def test_u_q7_matching_ignores_letter_case(token, categories):
    entry = parse_quick_entry(f"100 {token}", categories)
    assert entry.category.name == "Market"


@pytest.mark.parametrize("token", ["yakıt", "yakit", "YAKIT", "Yakıt"])
def test_u_q7b_matching_ignores_turkish_diacritics(token, categories):
    """Türkçe karakter yazmadan da kategori bulunabilmelidir."""
    entry = parse_quick_entry(f"100 {token}", categories)
    assert entry.category.name == "Yakıt"


def test_u_q8_inactive_categories_do_not_match(categories):
    entry = parse_quick_entry("100 eğlence", categories)
    assert entry.category is None
    assert entry.description == "eğlence"


def test_u_q9_payment_method_is_never_inferred_from_the_text(categories):
    """`nakit` kelimesi ödeme yöntemi seçmez, açıklamaya girer."""
    entry = parse_quick_entry("100 market nakit", categories)
    assert entry.category.name == "Market"
    assert entry.description == "nakit"


def test_unmatched_second_word_becomes_part_of_the_description(categories):
    entry = parse_quick_entry("75 kahve içtim", categories)
    assert entry.amount_minor == 7_500
    assert entry.category is None
    assert entry.description == "kahve içtim"


def test_amount_formats_are_shared_with_the_form(categories):
    assert parse_quick_entry("1.250,50 market", categories).amount_minor == 125_050
    assert parse_quick_entry("1250,50 market", categories).amount_minor == 125_050
    assert parse_quick_entry("₺75 market", categories).amount_minor == 7_500


@pytest.mark.parametrize("text", ["0 market", "-5 market"])
def test_non_positive_amounts_are_not_expenses(text, categories):
    with pytest.raises(NotAnExpense):
        parse_quick_entry(text, categories)


def test_fold_normalises_turkish_letters():
    assert fold("Yakıt") == fold("yakit") == "yakit"
    assert fold("İÇME") == "icme"
    assert fold("Sağlık") == "saglik"
