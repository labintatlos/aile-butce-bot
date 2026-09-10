"""Kişisel yıllık bütçe.

Eşlerin ortak giderden bağımsız, kişi başı yıllık bir harcama hakkı vardır;
ayakkabı veya güneş gözlüğü gibi kişisel alışverişler bundan düşer. Tutar her
yıl ayrı saklanır: yıl sonunda artan tutar devretmez, geçmiş yılın bütçesi de
sonradan değişmez.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PersonalBudget(Base):
    __tablename__ = "personal_budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "year", name="uq_personal_budget_user_year"),
        CheckConstraint("amount_minor >= 0", name="ck_personal_budget_amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
