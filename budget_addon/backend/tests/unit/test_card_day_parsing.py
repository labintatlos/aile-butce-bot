"""Kart kurulum yazımının ayrıştırılması.

Kullanıcı yalnızca **hesap kesim gününü** girer; son ödeme tarihi ondan
türetilir. İsteyen ikinci bir sayıyla vadeyi (kaç gün sonra) belirtebilir,
çünkü bankalar arasında fark var.
"""

import pytest

from app.bot.settings_commands import parse_card_setup


@pytest.mark.parametrize(
    "text, expected",
    [
        ("26", (26, None)),
        ("kesim 26", (26, None)),
        ("hesapkesim 26", (26, None)),
        ("KESIM 26", (26, None)),
        ("26 vade 12", (26, 12)),
        ("kesim 26 vade 12", (26, 12)),
        ("vade 12 kesim 26", (26, 12)),
        ("26 12", (26, 12)),
    ],
)
def test_accepted_forms(text, expected):
    assert parse_card_setup(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "kesim", "kesim abc", "26 12 5", "kesim 26 vade", "yirmialti"],
)
def test_unclear_input_is_refused_rather_than_guessed(text):
    assert parse_card_setup(text) is None


def test_a_single_number_is_the_statement_day():
    """En sık kullanım: kullanıcı sadece kesim gününü yazar."""
    statement_day, offset_days = parse_card_setup("26")
    assert statement_day == 26
    assert offset_days is None


def test_labels_make_the_order_irrelevant():
    assert parse_card_setup("vade 12 kesim 26") == parse_card_setup("kesim 26 vade 12")
