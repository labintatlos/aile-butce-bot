"""Birikim hedefi.

"Tatil için Haziran'a kadar 50.000 TL" gibi bir hedef ve şimdiye kadar
biriktirilen tutar. Biriken tutar bir banka hesabından okunmaz; kişi kenara
ayırdıkça kendisi ekler. Hedefe ulaşmak için ayda ne kadar ayrılması gerektiği
saklanmaz, her seferinde bugünden hesaplanır (bkz. `services/savings.py`).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SavingsGoal(TimestampMixin, Base):
    __tablename__ = "savings_goals"
    __table_args__ = (
        CheckConstraint("target_minor > 0", name="ck_savings_goal_target_positive"),
        CheckConstraint("saved_minor >= 0", name="ck_savings_goal_saved_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    target_minor: Mapped[int] = mapped_column(BigInteger)
    saved_minor: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    target_date: Mapped[date] = mapped_column(Date)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SavingsGoal {self.name} {self.saved_minor}/{self.target_minor}>"
