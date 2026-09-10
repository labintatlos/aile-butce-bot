"""Kayıtların CSV olarak dışa aktarılması.

Veriler kullanıcınındır ve eklentiden bağımsız olarak açılabilmelidir. CSV,
Excel'den LibreOffice'e her yerde okunur ve bir gün bu eklenti kullanılmaz
olsa bile kayıtlar elde kalır.

Biçim kararları Türkçe Excel'e göre verildi ve ikisi de bilinçlidir:

- Ayraç **noktalı virgüldür**. Türkçe yerel ayarda Excel virgülü ondalık
  işareti sayar; virgülle ayrılmış bir dosya tek sütuna yapışık açılır.
- Tutarlar `1234,56` biçiminde, binlik ayraç olmadan yazılır. Böylece hem
  okunur hem de sayı olarak hesaba girer.

Dosya UTF-8 BOM ile başlar; BOM olmadan Excel Türkçe karakterleri bozar.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.category import Category
from ..models.expense import Expense
from ..models.income import Income
from ..models.user import User
from ..utils.time import month_bounds
from . import refunds, tags
from .finance.money import MINOR_UNITS_PER_MAJOR

DELIMITER = ";"
UTF8_BOM = "﻿"

EXPENSE_HEADERS = (
    "İşlem",
    "Tarih",
    "Tutar",
    "İade",
    "Net",
    "Kategori",
    "Ödeme",
    "Taksit",
    "Kişi",
    "Açıklama",
    "Etiketler",
)

INCOME_HEADERS = ("Tarih", "Tutar", "Kaynak", "Kişi", "Not")


def format_amount(minor: int) -> str:
    """`1234,56` — binlik ayraçsız, virgüllü ondalık.

    İşaret ayrı ele alınır: Python'un tam bölmesi negatif sayıda aşağı
    yuvarlar ve `-50` kuruş `-1,50` gibi yazılırdı.
    """
    sign = "-" if minor < 0 else ""
    value = abs(minor)
    return (
        f"{sign}{value // MINOR_UNITS_PER_MAJOR},"
        f"{value % MINOR_UNITS_PER_MAJOR:02d}"
    )


def _writer(buffer: io.StringIO):
    return csv.writer(buffer, delimiter=DELIMITER, lineterminator="\n")


async def expenses_csv(
    session: AsyncSession, *, start: date, end: date
) -> str:
    """Tarih aralığındaki harcamaları CSV metni olarak verir."""
    rows = (
        await session.scalars(
            select(Expense)
            .options(selectinload(Expense.installments))
            .where(
                Expense.deleted_at.is_(None),
                Expense.transaction_date >= start,
                Expense.transaction_date <= end,
            )
            .order_by(Expense.transaction_date, Expense.id)
        )
    ).all()

    categories = {
        category.id: category
        for category in (await session.scalars(select(Category))).all()
    }
    people = {user.id: user for user in (await session.scalars(select(User))).all()}

    buffer = io.StringIO()
    writer = _writer(buffer)
    writer.writerow(EXPENSE_HEADERS)
    for expense in rows:
        refunded = await refunds.refunded_total(session, expense.id)
        category = categories.get(expense.category_id)
        person = people.get(expense.created_by_user_id)
        writer.writerow(
            [
                expense.public_id,
                expense.transaction_date.isoformat(),
                format_amount(expense.total_amount_minor),
                format_amount(refunded),
                format_amount(expense.total_amount_minor - refunded),
                category.name if category else "",
                expense.payment_method_name_snapshot,
                expense.installment_count,
                person.display_name if person else "",
                expense.description or "",
                " ".join(
                    f"#{tag}" for tag in await tags.tags_of(session, expense.id)
                ),
            ]
        )
    return UTF8_BOM + buffer.getvalue()


async def incomes_csv(session: AsyncSession, *, start: date, end: date) -> str:
    """Tarih aralığındaki gelirleri CSV metni olarak verir."""
    rows = (
        await session.scalars(
            select(Income)
            .where(
                Income.deleted_at.is_(None),
                Income.received_date >= start,
                Income.received_date <= end,
            )
            .order_by(Income.received_date, Income.id)
        )
    ).all()
    people = {user.id: user for user in (await session.scalars(select(User))).all()}

    buffer = io.StringIO()
    writer = _writer(buffer)
    writer.writerow(INCOME_HEADERS)
    for record in rows:
        person = people.get(record.created_by_user_id)
        writer.writerow(
            [
                record.received_date.isoformat(),
                format_amount(record.amount_minor),
                record.source,
                person.display_name if person else "",
                record.notes or "",
            ]
        )
    return UTF8_BOM + buffer.getvalue()


def month_range(year: int, month: int | None) -> tuple[date, date]:
    """Ay verilmişse o ayın, verilmemişse bütün yılın aralığı."""
    if month is None:
        return date(year, 1, 1), date(year, 12, 31)
    return month_bounds(year, month)


def filename_for(*, year: int, month: int | None, kind: str = "harcama") -> str:
    period = f"{year}-{month:02d}" if month else str(year)
    return f"butce-{kind}-{period}.csv"
