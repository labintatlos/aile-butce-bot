"""Takvim aritmetiği.

Kredi kartı hesap kesim ve son ödeme günleri ayın günü olarak saklanır. Her ay
o günü içermediği için (31 Şubat yoktur) tüm tarih üretimi buradaki tek
normalizasyon kuralından geçer.

Kurallar için bkz. docs/FINANCE_RULES.md, bölüm 3.
"""

from __future__ import annotations

import calendar
from datetime import date

MIN_DAY_OF_MONTH = 1
MAX_DAY_OF_MONTH = 31
MONTHS_PER_YEAR = 12


def validate_day_of_month(day: int) -> int:
    if not MIN_DAY_OF_MONTH <= day <= MAX_DAY_OF_MONTH:
        raise ValueError(
            f"Gün {MIN_DAY_OF_MONTH} ile {MAX_DAY_OF_MONTH} arasında olmalıdır"
        )
    return day


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def normalized_date(year: int, month: int, preferred_day: int) -> date:
    """Ayda bulunmayan günü ayın son gününe indirir.

    `normalized_date(2027, 2, 31)` -> 2027-02-28
    `normalized_date(2028, 2, 31)` -> 2028-02-29 (artık yıl)
    """
    validate_day_of_month(preferred_day)
    return date(year, month, min(preferred_day, last_day_of_month(year, month)))


def add_months(value: date, months: int, preferred_day: int | None = None) -> date:
    """Tarihe ay ekler ve tercih edilen günü korur.

    `preferred_day` verildiğinde her ay o gün hedeflenir. Bu önemlidir: bir
    önceki ayda ay sonuna indirilmiş bir gün, sonraki aya taşınmaz.

        add_months(date(2027, 2, 28), 1, preferred_day=31) -> 2027-03-31

    `preferred_day` verilmezse kaynak tarihin günü korunur.
    """
    absolute_month = value.year * MONTHS_PER_YEAR + (value.month - 1) + months
    year, month_index = divmod(absolute_month, MONTHS_PER_YEAR)
    return normalized_date(year, month_index + 1, preferred_day or value.day)
