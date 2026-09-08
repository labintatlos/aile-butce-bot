"""Harcama kaydı.

Kart koşullarının anlık görüntüsü (`*_snapshot`) burada saklanır: kart ayarı
sonradan değişse bile bu harcamanın taksit planı yeniden hesaplanmaz.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .payment_method import DEFAULT_CURRENCY

PUBLIC_ID_PREFIX = "EXP"
PUBLIC_ID_DIGITS = 6


def format_public_id(expense_id: int) -> str:
    """`EXP-000184` biçiminde, kullanıcıya gösterilen kimlik üretir."""
    return f"{PUBLIC_ID_PREFIX}-{expense_id:0{PUBLIC_ID_DIGITS}d}"


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("total_amount_minor > 0", name="ck_expense_amount_positive"),
        CheckConstraint(
            "installment_count BETWEEN 1 AND 12", name="ck_expense_installment_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )

    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    total_amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    installment_count: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # --- Harcama anindaki kart kosullarinin anlik goruntusu ---
    payment_method_type_snapshot: Mapped[str] = mapped_column(String(16))
    payment_method_name_snapshot: Mapped[str] = mapped_column(String(64))
    statement_day_snapshot: Mapped[int | None] = mapped_column(Integer, default=None)
    due_day_snapshot: Mapped[int | None] = mapped_column(Integer, default=None)
    cutoff_inclusive_snapshot: Mapped[bool | None] = mapped_column(Boolean, default=None)

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )

    installments: Mapped[list["ExpenseInstallment"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseInstallment.installment_number",
        # Asenkron oturumda tembel yukleme ortuk IO demektir ve MissingGreenlet
        # hatasi verir; taksitler her zaman ust kayitla birlikte yuklenir.
        lazy="selectin",
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Expense {self.public_id} {self.total_amount_minor}kr>"
