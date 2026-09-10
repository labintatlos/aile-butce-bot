"""Harcama arama ve filtreleme (§25).

Tüm sorgular SQLAlchemy ifadeleriyle, parametre bağlama ile kurulur; kullanıcı
metni hiçbir zaman SQL'e birleştirilmez.

Arama metnindeki `%` ve `_` karakterleri kaçırılır: aksi halde `%` yazan bir
kullanıcı farkında olmadan tüm kayıtları eşleştirirdi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.expense import Expense

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """`%`, `_` ve kaçış karakterini düz metin hâline getirir."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


@dataclass(frozen=True, slots=True)
class SearchFilters:
    text: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    category_id: int | None = None
    payment_method_id: int | None = None
    created_by_user_id: int | None = None
    min_amount_minor: int | None = None
    max_amount_minor: int | None = None


@dataclass(frozen=True, slots=True)
class SearchPage:
    items: list[Expense] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def _apply_filters(statement: Select, filters: SearchFilters) -> Select:
    # Yumusak silinmis kayitlar hicbir aramada gorunmez.
    statement = statement.where(Expense.deleted_at.is_(None))

    if filters.text:
        pattern = f"%{escape_like(filters.text)}%"
        # SQLite'ta LIKE ASCII icin buyuk/kucuk harf duyarsizdir; Turkce
        # harfler icin de calissin diye iki yon birlikte denenir.
        statement = statement.where(
            or_(
                Expense.description.ilike(pattern, escape=LIKE_ESCAPE),
                Expense.public_id.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if filters.date_from:
        statement = statement.where(Expense.transaction_date >= filters.date_from)
    if filters.date_to:
        statement = statement.where(Expense.transaction_date <= filters.date_to)
    if filters.category_id:
        statement = statement.where(Expense.category_id == filters.category_id)
    if filters.payment_method_id:
        statement = statement.where(Expense.payment_method_id == filters.payment_method_id)
    if filters.created_by_user_id:
        statement = statement.where(
            Expense.created_by_user_id == filters.created_by_user_id
        )
    if filters.min_amount_minor is not None:
        statement = statement.where(Expense.total_amount_minor >= filters.min_amount_minor)
    if filters.max_amount_minor is not None:
        statement = statement.where(Expense.total_amount_minor <= filters.max_amount_minor)
    return statement


async def search_expenses(
    session: AsyncSession,
    filters: SearchFilters,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> SearchPage:
    """Filtrelere uyan harcamaları sayfalayarak döndürür.

    Sonuçlar en yeni işlemden eskiye sıralanır; eşit tarihlerde kayıt sırası
    belirleyicidir, böylece sayfalar arasında kayıt tekrarlanmaz veya atlanmaz.
    """
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    total = await session.scalar(
        _apply_filters(select(func.count(Expense.id)), filters)
    )

    rows = await session.scalars(
        _apply_filters(
            select(Expense).options(
                selectinload(Expense.installments),
                selectinload(Expense.category),
                selectinload(Expense.created_by),
            ),
            filters,
        )
        .order_by(Expense.transaction_date.desc(), Expense.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    return SearchPage(
        items=list(rows.all()), total=total or 0, page=page, page_size=page_size
    )
