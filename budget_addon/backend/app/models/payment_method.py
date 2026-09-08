"""Ödeme yöntemleri: nakit ve kredi kartları.

Kart koşulları burada yaşar, ancak harcama oluşturulurken bu değerlerin bir
anlık görüntüsü `expenses` tablosuna kopyalanır. Buradaki bir değişiklik
geçmiş taksit planlarını **etkilemez** (docs/FINANCE_RULES.md, kural E5).
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

TYPE_CASH = "cash"
TYPE_CREDIT_CARD = "credit_card"
PAYMENT_METHOD_TYPES = (TYPE_CASH, TYPE_CREDIT_CARD)

DEFAULT_CURRENCY = "TRY"


class PaymentMethod(TimestampMixin, Base):
    __tablename__ = "payment_methods"
    __table_args__ = (
        CheckConstraint(
            f"type IN ('{TYPE_CASH}', '{TYPE_CREDIT_CARD}')",
            name="ck_payment_method_type",
        ),
        # Nakitte ekstre kavrami yoktur.
        CheckConstraint(
            f"type <> '{TYPE_CASH}' OR (statement_day IS NULL AND due_day IS NULL)",
            name="ck_cash_has_no_statement_days",
        ),
        # Kredi kartinda her iki gun de zorunlu ve 1-31 araliginda olmalidir.
        # NULL kontrolleri acikca yazilir: SQL'de NULL BETWEEN ... sonucu NULL'dur
        # ve CHECK kisiti NULL sonucu gecerli sayar, yani yalnizca BETWEEN yazmak
        # yarim yapilandirilmis bir karti engellemezdi.
        CheckConstraint(
            f"type <> '{TYPE_CREDIT_CARD}' OR ("
            "statement_day IS NOT NULL AND due_day IS NOT NULL "
            "AND statement_day BETWEEN 1 AND 31 "
            "AND due_day BETWEEN 1 AND 31)",
            name="ck_credit_card_days_in_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(16))
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), default=None
    )
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)

    statement_day: Mapped[int | None] = mapped_column(Integer, default=None)
    due_day: Mapped[int | None] = mapped_column(Integer, default=None)
    cutoff_inclusive: Mapped[bool] = mapped_column(Boolean, default=True)
    credit_limit_minor: Mapped[int | None] = mapped_column(BigInteger, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def is_credit_card(self) -> bool:
        return self.type == TYPE_CREDIT_CARD

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PaymentMethod {self.name} ({self.type})>"
