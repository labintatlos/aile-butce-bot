"""Bölünmüş harcamanın parçası.

Tek bir fiş birden çok kategoriye ait olabilir: 1.200 TL'lik market fişinin
900 TL'si gıda, 300 TL'si temizlik. Harcama tek kalır (tek tutar, tek kart,
tek taksit planı); yalnızca kategori dağılımı parçalara ayrılır.

Parçaların toplamı her zaman harcamanın tutarına **eşittir**. Bu kural
`services/expenses.py` içinde, harcamayla aynı transaction'da doğrulanır.
Bölünmemiş bir harcamanın parçası yoktur; kategorisi doğrudan
`expenses.category_id` alanındadır.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .category import Category
    from .expense import Expense


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_expense_split_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(String(200), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(lazy="selectin")
    expense: Mapped[Expense] = relationship(back_populates="splits")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExpenseSplit {self.category_id} {self.amount_minor}kr>"
