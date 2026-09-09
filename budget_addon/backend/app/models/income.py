"""Gelir kaydı.

Sistem bugüne kadar yalnızca paranın çıkışını biliyordu; bu yüzden "bu ay ne
kadar harcadım" sorusunu yanıtlayabiliyor ama "ay sonunda ne kalacak"
sorusunu yanıtlayamıyordu. Gelir kaydı o boşluğu kapatır.

Harcamalar gibi yumuşak silinir: silinen bir gelir raporlardan çıkar ama
denetim izi korunur.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .payment_method import DEFAULT_CURRENCY


class Income(TimestampMixin, Base):
    __tablename__ = "incomes"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_income_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    received_date: Mapped[date] = mapped_column(Date, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    source: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<Income {self.source} {self.amount_minor}>"
