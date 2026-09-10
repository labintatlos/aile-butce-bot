"""Hesap kesim ve son ödeme tarihi hesabı.

Kullanıcı yalnızca **hesap kesim gününü** girer. Son ödeme tarihi bundan
türetilir: ekstre kesildikten `due_offset_days` gün sonra, o gün hafta sonuna
veya resmî tatile denk gelirse ilk iş gününe taşınarak.

Kurallar için bkz. docs/FINANCE_RULES.md, bölüm 4, 5 ve 6.
"""

from __future__ import annotations

from datetime import date, timedelta

from .dates import add_months, next_business_day, normalized_date, validate_day_of_month

ONE_MONTH = 1

DEFAULT_DUE_OFFSET_DAYS = 10
"""Ekstre kesimi ile son ödeme arasındaki gün sayısı.

Türkiye'de yaygın uygulama 10 gündür, ancak bankadan bankaya değişir; bu
yüzden kart bazında ayarlanabilir tutulur. Yanlış bir gün sayısı, sistemin
hata vermeden her ay yanlış son ödeme tarihi üretmesine yol açardı.
"""

MIN_DUE_OFFSET_DAYS = 1
MAX_DUE_OFFSET_DAYS = 60


def validate_due_offset(offset_days: int) -> int:
    if not MIN_DUE_OFFSET_DAYS <= offset_days <= MAX_DUE_OFFSET_DAYS:
        raise ValueError(
            f"Son ödeme gün farkı {MIN_DUE_OFFSET_DAYS} ile {MAX_DUE_OFFSET_DAYS}"
            " arasında olmalıdır"
        )
    return offset_days


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


def due_date_for(
    statement_date: date, offset_days: int = DEFAULT_DUE_OFFSET_DAYS
) -> date:
    """Bir ekstrenin son ödeme tarihini bulur.

    Ekstre tarihine `offset_days` gün eklenir; sonuç hafta sonuna veya resmî
    tatile denk gelirse ilk iş gününe taşınır, çünkü bankalar o günlerde
    tahsilat yapmaz.

    Ay sonu normalizasyonuna gerek yoktur: gün ekleme zaten takvimi doğru
    takip eder ve 31 Ocak + 10 gün gibi bir durumda ayın var olmayan gününe
    düşme sorunu oluşmaz.
    """
    validate_due_offset(offset_days)
    return next_business_day(statement_date + timedelta(days=offset_days))
