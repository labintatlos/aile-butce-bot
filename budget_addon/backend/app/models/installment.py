"""Taksit satırı.

Ekstre ve son ödeme tarihleri hesaplanıp **saklanır**; okurken yeniden
hesaplanmaz. Bu, kart ayarı değişse bile geçmişin sabit kalmasını sağlar ve
ileride taksit bazında manuel tarih düzeltmesi eklemeyi mümkün kılar.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

STATUS_SCHEDULED = "scheduled"
STATUS_PAID = "paid"
STATUS_CANCELLED = "cancelled"
INSTALLMENT_STATUSES = (STATUS_SCHEDULED, STATUS_PAID, STATUS_CANCELLED)

ACTIVE_STATUSES = (STATUS_SCHEDULED,)


class ExpenseInstallment(Base):
    __tablename__ = "expense_installments"
    __table_args__ = (
        UniqueConstraint(
            "expense_id", "installment_number", name="uq_installment_number_per_expense"
        ),
        CheckConstraint(
            "status IN ('scheduled', 'paid', 'cancelled')", name="ck_installment_status"
        ),
        CheckConstraint(
            "installment_number BETWEEN 1 AND installment_count",
            name="ck_installment_number_within_count",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )

    installment_number: Mapped[int] = mapped_column(Integer)
    installment_count: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)

    statement_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_SCHEDULED, index=True)

    created_at: Mapped[date] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    expense: Mapped["Expense"] = relationship(back_populates="installments")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Installment {self.installment_number}/{self.installment_count} "
            f"{self.amount_minor}kr {self.statement_date}>"
        )
