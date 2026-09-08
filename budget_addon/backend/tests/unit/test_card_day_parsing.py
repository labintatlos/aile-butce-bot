"""Kart günü yazımının ayrıştırılması.

`26 10` biçiminde iki çıplak sayının hangisinin ne olduğu anlaşılmadığı için
etiketli yazım da kabul edilir. Etiket kullanıldığında sıra önemsizdir.
"""

import pytest

from app.bot.settings_commands import parse_card_days


@pytest.mark.parametrize(
    "text, expected",
    [
        ("26 10", (26, 10)),
        ("kesim 26 sonodeme 10", (26, 10)),
        ("sonodeme 10 kesim 26", (26, 10)),
        ("hesapkesim 5 ödeme 20", (5, 20)),
        ("KESIM 26 SONODEME 10", (26, 10)),
    ],
)
def test_accepted_forms(text, expected):
    assert parse_card_days(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "abc", "kesim 26", "sonodeme 10", "26", "26 10 5", "kesim abc sonodeme 10"],
)
def test_ambiguous_or_incomplete_input_is_refused(text):
    """Eksik veya belirsiz girdide tahmin yürütülmez."""
    assert parse_card_days(text) is None


def test_labelled_form_does_not_fall_back_to_positional():
    """Etiket kullanıldıysa eksik etiket sessizce sıraya dönmemelidir."""
    assert parse_card_days("kesim 26 10") is None
