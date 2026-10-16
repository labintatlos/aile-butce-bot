"""Hesaplar ve hesap hareketleri: bakiye, transfer ve net varlık.

Vadesiz hesap, nakit, birikim ve yatırım hesaplarının bakiyesi buradan
izlenir. Bakiye banka hesabından **okunmaz**: kişi bakiyeyi zaman zaman
günceller (`balance` kaydı), arada hesaplar arası transfer girebilir.

Bir tarihteki bakiye şöyle bulunur: o tarihe kadarki son `balance` kaydı
başlangıçtır, ondan sonraki transfer ve düzeltmeler üzerine eklenir. Böylece
geçmişe dönük bir bakiye girişi sonraki transferleri bozmaz.

Transfer harcama **değildir**: vadesiz hesaptan birikime aktarılan para
raporlarda harcama ya da gelir olarak görünmez, yalnızca iki hesabın
bakiyesini değiştirir. İki ayağı aynı `transfer_group` ile bağlanır ve
birlikte silinir.
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

KIND_BANK = "bank"
KIND_CASH = "cash"
KIND_SAVINGS = "savings"
KIND_INVESTMENT = "investment"
KIND_OTHER = "other"
ACCOUNT_KINDS = (KIND_BANK, KIND_CASH, KIND_SAVINGS, KIND_INVESTMENT, KIND_OTHER)

ENTRY_BALANCE = "balance"
"""Hesabın o günkü bakiyesi; tutar mutlak değerdir."""
ENTRY_TRANSFER = "transfer"
"""Hesaplar arası aktarım ayağı veya kart ödemesi; tutar işaretli farktır."""
ENTRY_ADJUSTMENT = "adjustment"
"""Faiz, masraf gibi elle girilen işaretli fark."""
ENTRY_KINDS = (ENTRY_BALANCE, ENTRY_TRANSFER, ENTRY_ADJUSTMENT)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('bank', 'cash', 'savings', 'investment', 'other')",
            name="ck_account_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default=KIND_BANK)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(String(200), default=None)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Account {self.name}>"


class AccountEntry(Base):
    __tablename__ = "account_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('balance', 'transfer', 'adjustment')", name="ck_account_entry_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    transfer_group: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    payment_method_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """Kart ödemesinde ödenen kart. Kart borcu taksitlerden hesaplandığı için
    yalnızca bilgi amaçlıdır."""
    note: Mapped[str | None] = mapped_column(String(200), default=None)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AccountEntry {self.kind} {self.amount_minor}kr>"
