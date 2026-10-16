"""Ekstre mutabakatı.

Bankanın kestiği ekstre tutarı ile sistemin hesapladığı tutar yan yana
konur. Fark varsa ya bir harcama girilmemiştir ya da yanlış girilmiştir;
mutabakat kaydı bu karşılaştırmanın hangi tutarla yapıldığını saklar.

Sistemin o andaki hesabı (`ours_total_minor`) da saklanır: sonradan geçmiş bir
harcama düzenlenirse "mutabık" denen ekstrenin bozulduğu görülebilsin.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class StatementReconciliation(TimestampMixin, Base):
    __tablename__ = "statement_reconciliations"
    __table_args__ = (
        UniqueConstraint(
            "payment_method_id", "statement_date", name="uq_reconciliation_statement"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="CASCADE"), index=True
    )
    statement_date: Mapped[date] = mapped_column(Date)
    bank_total_minor: Mapped[int] = mapped_column(BigInteger)
    ours_total_minor: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(String(200), default=None)
    reconciled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reconciliation {self.payment_method_id} {self.statement_date}>"
