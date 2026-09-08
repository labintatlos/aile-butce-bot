"""Arama metni kaçırma testleri.

Saf fonksiyon olduğu için veritabanı olmadan sınanır. Kaçırma başarısız
olursa `%` yazan bir kullanıcı farkında olmadan tüm kayıtları eşleştirir.
"""

from app.services.search import escape_like


def test_percent_becomes_literal():
    assert escape_like("100%") == "100\\%"


def test_underscore_becomes_literal():
    assert escape_like("a_b") == "a\\_b"


def test_escape_character_itself_is_escaped_first():
    assert escape_like("c:\\yol") == "c:\\\\yol"


def test_ordinary_text_is_untouched():
    assert escape_like("Migros alışverişi") == "Migros alışverişi"
