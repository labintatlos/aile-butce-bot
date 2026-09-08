"""Hesap kesim ve son ödeme tarihi hesabı.

Kurallar için bkz. docs/FINANCE_RULES.md, bölüm 4, 5 ve 6.
"""

from __future__ import annotations

from datetime import date

from .dates import add_months, normalized_date, validate_day_of_month

ONE_MONTH = 1
SAME_MONTH = 0


def first_statement_date(
    transaction_date: date,
    statement_day: int,
    cutoff_inclusive: bool = True,
) -> date:
    """Harcamanın ilk kez hangi ekstreye düşeceğini bulur.

    İşlem tarihi, işlem ayındaki hesap kesim tarihinden önceyse o ekstreye
    girer. Tam olarak hesap kesim gününde yapılan harcamanın akıbetini kart
    ayarındaki `cutoff_inclusive` belirler; `False` ise takip eden ekstreye
    kayar.
    """
    validate_day_of_month(statement_day)
    candidate = normalized_date(
        transaction_date.year, transaction_date.month, statement_day
    )
    if transaction_date < candidate:
        return candidate
    if transaction_date == candidate and cutoff_inclusive:
        return candidate
    return add_months(candidate, ONE_MONTH, statement_day)


def due_date_for(statement_date: date, statement_day: int, due_day: int) -> date:
    """Bir ekstrenin son ödeme tarihini bulur.

    Karar, kartın **yapılandırılmış ham günleri** üzerinden verilir; ay sonu
    normalizasyonu sonrası oluşan günler karşılaştırmaya girmez. Aksi halde
    `statement_day=31, due_day=10` gibi bir kart Şubat'ta yanlış aya kayardı.
    """
    validate_day_of_month(statement_day)
    validate_day_of_month(due_day)
    month_offset = SAME_MONTH if due_day > statement_day else ONE_MONTH
    return add_months(statement_date, month_offset, due_day)
