"""Harcama kategorileri."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    emoji: Mapped[str] = mapped_column(String(8), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_budget_minor: Mapped[int | None] = mapped_column(
        BigInteger, default=None
    )
    """Bu kategori için aylık harcama hedefi, kuruş cinsinden.

    Boş bırakılabilir: hedefi olmayan kategori hiçbir uyarı üretmez ve
    raporda yalnızca tutarıyla görünür. Hedef bir sınır değil ölçüdür;
    aşıldığında harcama kaydı engellenmez, yalnızca haber verilir."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name}>"
