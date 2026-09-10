"""Tutar ve tarihlerin Türkçe gösterimi.

Bildirim metinleri, e-postalar ve dışa aktarmalar aynı sayıyı aynı şekilde
göstersin diye biçimlendirme tek yerde durur.
"""

from __future__ import annotations

from datetime import date

from ..services.finance.money import format_try

MONTH_NAMES = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)


def money(minor: int) -> str:
    """`12.450,75 TL`"""
    return format_try(minor)


def short_date(value: date) -> str:
    """`02.09.2026`"""
    return value.strftime("%d.%m.%Y")


def long_date(value: date) -> str:
    """`2 Eylül 2026`"""
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def month_name(year: int, month: int) -> str:
    """`Eylül 2026`"""
    return f"{MONTH_NAMES[month - 1]} {year}"
