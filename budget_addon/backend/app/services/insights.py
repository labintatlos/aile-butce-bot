"""Ayrıntılı raporlar: kategori × ay tablosu, nakit akışı geçmişi, günlük
harcama ve gelirden kategorilere para akışı.

Hepsi **harcama** bakışıdır (bkz. `services/reports.py`): tutar harcamanın
yapıldığı aya yazılır, taksit sayısı etkilemez. İadeler alındıkları aydan
düşülür. Bölünmüş harcamanın parçaları kendi kategorilerine yazılır.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.category import Category
from ..models.expense import Expense
from ..models.income import Income
from ..models.refund import Refund
from ..utils.time import month_bounds
from .allocation import refunded_by_category_month, spent_by_category_month
from .finance.dates import MONTHS_PER_YEAR

UNGROUPED = "Diğer"


# ---------------------------------------------------------------------------
# Kategori × ay
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatrixRow:
    category_id: int
    name: str
    emoji: str
    group_name: str
    months: list[int]

    @property
    def total_minor(self) -> int:
        return sum(self.months)


@dataclass(frozen=True, slots=True)
class CategoryMatrix:
    year: int
    rows: list[MatrixRow]

    @property
    def month_totals(self) -> list[int]:
        return [sum(row.months[index] for row in self.rows) for index in range(MONTHS_PER_YEAR)]

    @property
    def total_minor(self) -> int:
        return sum(self.month_totals)


async def category_matrix(session: AsyncSession, *, year: int) -> CategoryMatrix:
    """Bir yılın kategori × ay net harcama tablosu.

    Yıl içinde hiç hareketi olmayan kategori listeye girmez. Satırlar grup,
    sonra yıllık toplam sırasıyla dizilir.
    """
    start, end = date(year, 1, 1), date(year, 12, 31)
    spent = await spent_by_category_month(session, start=start, end=end)
    refunded = await refunded_by_category_month(session, start=start, end=end)
    cells: dict[int, list[int]] = defaultdict(lambda: [0] * MONTHS_PER_YEAR)
    for (category_id, _year, month), amount in spent.items():
        cells[category_id][month - 1] += amount
    for (category_id, _year, month), amount in refunded.items():
        cells[category_id][month - 1] -= amount
    if not cells:
        return CategoryMatrix(year=year, rows=[])
    categories = {
        category.id: category
        for category in (
            await session.scalars(select(Category).where(Category.id.in_(cells)))
        ).all()
    }
    rows = [
        MatrixRow(
            category_id=category_id,
            name=categories[category_id].name,
            emoji=categories[category_id].emoji,
            group_name=categories[category_id].group_name or UNGROUPED,
            months=months,
        )
        for category_id, months in cells.items()
        if category_id in categories
    ]
    group_totals: dict[str, int] = defaultdict(int)
    for row in rows:
        group_totals[row.group_name] += row.total_minor
    rows.sort(key=lambda row: (-group_totals[row.group_name], row.group_name, -row.total_minor))
    return CategoryMatrix(year=year, rows=rows)


# ---------------------------------------------------------------------------
# Nakit akışı geçmişi
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlowMonth:
    year: int
    month: int
    income_minor: int
    spending_minor: int

    @property
    def net_minor(self) -> int:
        return self.income_minor - self.spending_minor


def _last_months(today: date, months: int) -> list[tuple[int, int]]:
    current = today.year * MONTHS_PER_YEAR + (today.month - 1)
    result = []
    for index in range(current - months + 1, current + 1):
        year, month_index = divmod(index, MONTHS_PER_YEAR)
        result.append((year, month_index + 1))
    return result


async def _monthly_sums(session: AsyncSession, column, amount, conditions, start, end):
    year = func.strftime("%Y", column)
    month = func.strftime("%m", column)
    rows = await session.execute(
        select(year, month, func.sum(amount))
        .where(*conditions, column >= start, column <= end)
        .group_by(year, month)
    )
    return {(int(row[0]), int(row[1])): int(row[2]) for row in rows.all()}


async def cashflow_history(
    session: AsyncSession, *, today: date, months: int = 12
) -> list[FlowMonth]:
    """Son `months` ayın gelir, net harcama ve farkı; içinde bulunulan ay dahil."""
    span = _last_months(today, months)
    start, _ = month_bounds(*span[0])
    _, end = month_bounds(*span[-1])
    income = await _monthly_sums(
        session, Income.received_date, Income.amount_minor, (Income.deleted_at.is_(None),), start, end
    )
    spending = await _monthly_sums(
        session,
        Expense.transaction_date,
        Expense.total_amount_minor,
        (Expense.deleted_at.is_(None),),
        start,
        end,
    )
    refunds = await _monthly_sums(
        session, Refund.refund_date, Refund.amount_minor, (Refund.deleted_at.is_(None),), start, end
    )
    return [
        FlowMonth(
            year=year,
            month=month,
            income_minor=income.get((year, month), 0),
            spending_minor=spending.get((year, month), 0) - refunds.get((year, month), 0),
        )
        for year, month in span
    ]


# ---------------------------------------------------------------------------
# Günlük harcama
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DailySpending:
    year: int
    month: int
    days: list[int]
    """Ayın her günü için net harcama; indeks 0 ayın 1'idir."""

    @property
    def total_minor(self) -> int:
        return sum(self.days)


async def daily_spending(session: AsyncSession, *, year: int, month: int) -> DailySpending:
    start, end = month_bounds(year, month)
    days = [0] * end.day
    rows = await session.execute(
        select(Expense.transaction_date, func.sum(Expense.total_amount_minor))
        .where(
            Expense.deleted_at.is_(None),
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
        .group_by(Expense.transaction_date)
    )
    for when, amount in rows.all():
        days[when.day - 1] += int(amount)
    refund_rows = await session.execute(
        select(Refund.refund_date, func.sum(Refund.amount_minor))
        .where(Refund.deleted_at.is_(None), Refund.refund_date >= start, Refund.refund_date <= end)
        .group_by(Refund.refund_date)
    )
    for when, amount in refund_rows.all():
        days[when.day - 1] -= int(amount)
    return DailySpending(year=year, month=month, days=days)


# ---------------------------------------------------------------------------
# Para akışı (gelir → gruplar)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlowNode:
    name: str
    amount_minor: int
    categories: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MoneyFlow:
    year: int
    month: int
    sources: list[FlowNode]
    """Gelir kaynakları."""
    targets: list[FlowNode]
    """Harcama grupları ve içlerindeki kategoriler."""

    @property
    def income_minor(self) -> int:
        return sum(node.amount_minor for node in self.sources)

    @property
    def spending_minor(self) -> int:
        return sum(node.amount_minor for node in self.targets)

    @property
    def remaining_minor(self) -> int:
        """Gelirden harcandıktan sonra kalan; açık varsa eksidir."""
        return self.income_minor - self.spending_minor


async def money_flow(session: AsyncSession, *, year: int, month: int) -> MoneyFlow:
    """Bir ayda gelirin hangi kaynaklardan gelip hangi gruplara gittiği."""
    start, end = month_bounds(year, month)
    income_rows = await session.execute(
        select(Income.source, func.sum(Income.amount_minor))
        .where(Income.deleted_at.is_(None), Income.received_date >= start, Income.received_date <= end)
        .group_by(Income.source)
        .order_by(func.sum(Income.amount_minor).desc())
    )
    sources = [FlowNode(name=row[0], amount_minor=int(row[1])) for row in income_rows.all()]

    matrix = await category_matrix(session, year=year)
    groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in matrix.rows:
        amount = row.months[month - 1]
        if amount > 0:
            label = f"{row.emoji} {row.name}".strip()
            groups[row.group_name].append((label, amount))
    targets = [
        FlowNode(
            name=name,
            amount_minor=sum(amount for _, amount in items),
            categories=sorted(items, key=lambda item: -item[1]),
        )
        for name, items in groups.items()
    ]
    targets.sort(key=lambda node: -node.amount_minor)
    return MoneyFlow(year=year, month=month, sources=sources, targets=targets)
