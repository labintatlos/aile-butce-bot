"""Taksit planı üretimi.

Bu modül saf fonksiyonlardan oluşur: veritabanı, ağ veya "şu an" bağımlılığı
yoktur. Üretilen plan, harcama ile aynı veritabanı işlemi içinde yazılır ve
kart ayarları sonradan değişse bile bir daha hesaplanmaz.

Kurallar için bkz. docs/FINANCE_RULES.md, bölüm 2, 5 ve 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .money import MAX_INSTALLMENTS, MIN_INSTALLMENTS, split_minor
from .statement import DEFAULT_DUE_OFFSET_DAYS, due_date_for, first_statement_date

SINGLE_INSTALLMENT = 1


@dataclass(frozen=True, slots=True)
class InstallmentLine:
    """Tek bir taksit satırı. Tutar kuruş cinsindendir."""

    number: int
    count: int
    amount_minor: int
    statement_date: date
    due_date: date


def build_cash_schedule(total_minor: int, transaction_date: date) -> list[InstallmentLine]:
    """Nakit harcama için tek satırlık plan üretir.

    Nakit ödemede ekstre kavramı yoktur; ödeme işlem günü gerçekleşir, bu
    yüzden ekstre ve son ödeme tarihi işlem tarihine eşitlenir.
    """
    if total_minor <= 0:
        raise ValueError("Toplam tutar sıfırdan büyük olmalıdır")
    return [
        InstallmentLine(
            number=SINGLE_INSTALLMENT,
            count=SINGLE_INSTALLMENT,
            amount_minor=total_minor,
            statement_date=transaction_date,
            due_date=transaction_date,
        )
    ]


def build_card_schedule(
    *,
    total_minor: int,
    installment_count: int,
    transaction_date: date,
    statement_day: int,
    due_offset_days: int = DEFAULT_DUE_OFFSET_DAYS,
    cutoff_inclusive: bool = True,
) -> list[InstallmentLine]:
    """Kredi kartı harcaması için taksit planı üretir.

    İlk ekstre tarihi kartın hesap kesim gününe göre bulunur, sonraki taksitler
    birer ay ilerler. Tutar kuruş kaybı olmadan bölünür.
    """
    amounts = split_minor(total_minor, installment_count)
    opening_statement = first_statement_date(
        transaction_date, statement_day, cutoff_inclusive
    )
    schedule = [
        _line_for(
            index, amount, opening_statement, installment_count, statement_day,
            due_offset_days,
        )
        for index, amount in enumerate(amounts)
    ]
    _verify_invariants(schedule, total_minor, installment_count)
    return schedule


def _line_for(
    index: int,
    amount_minor: int,
    opening_statement: date,
    installment_count: int,
    statement_day: int,
    due_offset_days: int,
) -> InstallmentLine:
    from .dates import add_months

    statement = add_months(opening_statement, index, statement_day)
    return InstallmentLine(
        number=index + 1,
        count=installment_count,
        amount_minor=amount_minor,
        statement_date=statement,
        due_date=due_date_for(statement, due_offset_days),
    )


def _verify_invariants(
    schedule: list[InstallmentLine], total_minor: int, installment_count: int
) -> None:
    """Planı döndürmeden önce finansal değişmez kuralları doğrular.

    `assert` yerine açık kontrol kullanılır: `assert` ifadeleri `python -O` ile
    kaldırılır ve üretimde sessizce devre dışı kalırdı.
    """
    if sum(line.amount_minor for line in schedule) != total_minor:
        raise AssertionError("Taksit toplamı harcama toplamına eşit değil")
    if len(schedule) != installment_count:
        raise AssertionError("Üretilen taksit sayısı beklenenden farklı")
    statements = [line.statement_date for line in schedule]
    if statements != sorted(statements) or len(set(statements)) != len(statements):
        raise AssertionError("Ekstre tarihleri kesin artan sırada değil")


def build_schedule(
    *,
    total_minor: int,
    installment_count: int,
    transaction_date: date,
    statement_day: int | None,
    due_offset_days: int | None = DEFAULT_DUE_OFFSET_DAYS,
    cutoff_inclusive: bool = True,
) -> list[InstallmentLine]:
    """Ödeme yöntemine göre uygun planı üretir.

    `statement_day` `None` ise ödeme nakit kabul edilir ve taksit sayısı 1
    olmak zorundadır.
    """
    if not MIN_INSTALLMENTS <= installment_count <= MAX_INSTALLMENTS:
        raise ValueError(
            f"Taksit sayısı {MIN_INSTALLMENTS} ile {MAX_INSTALLMENTS} arasında olmalıdır"
        )
    is_cash = statement_day is None
    if is_cash:
        if installment_count != SINGLE_INSTALLMENT:
            raise ValueError("Nakit harcamalarda taksit kullanılamaz")
        return build_cash_schedule(total_minor, transaction_date)
    return build_card_schedule(
        total_minor=total_minor,
        installment_count=installment_count,
        transaction_date=transaction_date,
        statement_day=statement_day,
        # `or` kullanilmaz: 0 yanlis bir deger ama falsy oldugu icin sessizce
        # varsayilana donusur ve gecersiz girdi fark edilmeden gecerdi.
        due_offset_days=(
            DEFAULT_DUE_OFFSET_DAYS if due_offset_days is None else due_offset_days
        ),
        cutoff_inclusive=cutoff_inclusive,
    )
