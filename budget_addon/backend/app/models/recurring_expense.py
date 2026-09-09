"""Sabit gider şablonu: kira, aidat, abonelik, okul taksiti.

Bu tablo bir harcama değil, **her ay hangi harcamanın oluşturulacağının
tarifidir**. Şablonun kendisi hiçbir rapora girmez; raporlara yalnızca ondan
üretilen gerçek `Expense` kayıtları girer. Böylece "gelecek 12 aylık yük"
raporu kredi kartı taksitlerinin yanında sabit giderleri de gerçek kayıtlar
üzerinden görebilir.

Tutar burada yalnızca **varsayılandır**. Kira zamlandığında şablon
güncellenir; geçmiş aylarda üretilmiş kayıtlar olduğu gibi kalır, çünkü
geçmiş yeniden hesaplanmaz.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .payment_method import DEFAULT_CURRENCY


class RecurringExpense(TimestampMixin, Base):
    __tablename__ = "recurring_expenses"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_recurring_amount_positive"),
        CheckConstraint(
            "day_of_month BETWEEN 1 AND 31", name="ck_recurring_day_in_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )

    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    day_of_month: Mapped[int] = mapped_column(Integer)
    """Ayın kaçında kaydedileceği.

    Ay o kadar gün sürmüyorsa (31 girilmiş bir şubat) ayın son gününe düşer;
    kural `finance/dates.normalized_date` içindedir ve taksit tarihleriyle
    aynıdır."""

    start_date: Mapped[date] = mapped_column(Date)
    """Şablonun ilk kez geçerli olduğu tarih.

    Bundan önceki aylar için kayıt üretilmez. Yeni tanımlanan bir kira, geçen
    ayın kirasını geriye dönük yazmamalıdır; ileri bir tarih verilerek
    "gelecek ay başlayacak abonelik" de tanımlanabilir."""

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<RecurringExpense {self.name} /{self.day_of_month}>"
