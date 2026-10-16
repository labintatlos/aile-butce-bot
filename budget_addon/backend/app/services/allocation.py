"""Harcamaların kategorilere dağılımı.

Bölünmemiş bir harcamanın tamamı kendi kategorisine yazılır; bölünmüş bir
harcamanın her parçası kendi kategorisine. Kategori toplamı üreten her rapor
(aylık harcama, bütçe hedefleri, dönem özetleri, kategori × ay tablosu)
buradaki satırlardan beslenir: biri parçaları unutup harcamanın tamamını tek
kategoriye yazarsa toplamlar sessizce yanlış olurdu.

İadeler de aynı kurala uyar. Bölünmüş bir harcamadan yapılan iade parçalara
tutarlarıyla orantılı paylaştırılır; kuruş kaybı olmaz.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import exists, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.expense_split import ExpenseSplit
from ..models.refund import Refund
from .finance.money import allocate_proportionally


def category_lines():
    """`(expense_id, category_id, amount_minor)` satırları.

    Bölünmemiş harcama tek satır, bölünmüş harcama parça sayısı kadar satır
    üretir. Çağıran taraf `Expense` ile birleştirip kendi süzgecini uygular.
    """
    has_split = exists().where(ExpenseSplit.expense_id == Expense.id)
    plain = select(
        Expense.id.label("expense_id"),
        Expense.category_id.label("category_id"),
        Expense.total_amount_minor.label("amount_minor"),
    ).where(~has_split)
    parts = select(
        ExpenseSplit.expense_id.label("expense_id"),
        ExpenseSplit.category_id.label("category_id"),
        ExpenseSplit.amount_minor.label("amount_minor"),
    )
    return union_all(plain, parts).subquery("category_lines")


async def spent_by_category(
    session: AsyncSession, *, start: date, end: date, expense_filter: tuple = ()
) -> dict[int, tuple[int, int]]:
    """Kategori kimliğine göre `(toplam, harcama sayısı)`; iadeler düşülmez."""
    lines = category_lines()
    rows = await session.execute(
        select(
            lines.c.category_id,
            func.coalesce(func.sum(lines.c.amount_minor), 0),
            func.count(func.distinct(lines.c.expense_id)),
        )
        .join(Expense, Expense.id == lines.c.expense_id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
            *expense_filter,
        )
        .group_by(lines.c.category_id)
    )
    return {row[0]: (int(row[1]), int(row[2])) for row in rows.all()}


async def spent_by_category_month(
    session: AsyncSession, *, start: date, end: date
) -> dict[tuple[int, int, int], int]:
    """`(kategori, yıl, ay)` anahtarıyla harcama toplamları; iadeler düşülmez."""
    lines = category_lines()
    year = func.strftime("%Y", Expense.transaction_date)
    month = func.strftime("%m", Expense.transaction_date)
    rows = await session.execute(
        select(lines.c.category_id, year, month, func.sum(lines.c.amount_minor))
        .join(Expense, Expense.id == lines.c.expense_id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
        .group_by(lines.c.category_id, year, month)
    )
    return {(row[0], int(row[1]), int(row[2])): int(row[3]) for row in rows.all()}


@dataclass(frozen=True, slots=True)
class RefundPiece:
    """Bir iadenin bir kategoriye düşen payı."""

    category_id: int
    refund_date: date
    amount_minor: int


async def refund_pieces(
    session: AsyncSession, *, start: date, end: date, expense_filter: tuple = ()
) -> list[RefundPiece]:
    """Tarih aralığındaki iadeleri kategori paylarına ayırır.

    Bölünmemiş harcamanın iadesi kayıt anında saklanan kategoriye düşer.
    Bölünmüş harcamanınki parçalara orantılı paylaştırılır.
    """
    statement = select(
        Refund.expense_id, Refund.category_id, Refund.refund_date, Refund.amount_minor
    ).where(
        Refund.deleted_at.is_(None),
        Refund.refund_date >= start,
        Refund.refund_date <= end,
    )
    if expense_filter:
        statement = statement.join(Expense, Refund.expense_id == Expense.id).where(
            *expense_filter
        )
    refunds = (await session.execute(statement)).all()
    if not refunds:
        return []

    split_rows = (
        await session.execute(
            select(ExpenseSplit.expense_id, ExpenseSplit.category_id, ExpenseSplit.amount_minor)
            .where(ExpenseSplit.expense_id.in_({row[0] for row in refunds}))
            .order_by(ExpenseSplit.expense_id, ExpenseSplit.position, ExpenseSplit.id)
        )
    ).all()
    splits: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for expense_id, category_id, amount in split_rows:
        splits[expense_id].append((category_id, amount))

    pieces = []
    for expense_id, category_id, refund_date, amount in refunds:
        parts = splits.get(expense_id)
        if not parts:
            pieces.append(RefundPiece(category_id, refund_date, amount))
            continue
        shares = allocate_proportionally(amount, [weight for _, weight in parts])
        pieces.extend(
            RefundPiece(part_category, refund_date, share)
            for (part_category, _), share in zip(parts, shares, strict=True)
            if share
        )
    return pieces


async def refunded_by_category(
    session: AsyncSession, *, start: date, end: date, expense_filter: tuple = ()
) -> dict[int, int]:
    totals: dict[int, int] = defaultdict(int)
    for piece in await refund_pieces(
        session, start=start, end=end, expense_filter=expense_filter
    ):
        totals[piece.category_id] += piece.amount_minor
    return dict(totals)


async def refunded_by_category_month(
    session: AsyncSession, *, start: date, end: date
) -> dict[tuple[int, int, int], int]:
    totals: dict[tuple[int, int, int], int] = defaultdict(int)
    for piece in await refund_pieces(session, start=start, end=end):
        key = (piece.category_id, piece.refund_date.year, piece.refund_date.month)
        totals[key] += piece.amount_minor
    return dict(totals)
