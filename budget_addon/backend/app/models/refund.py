"""İade kaydı.

Bir ürün geri verildiğinde harcamayı silmek yanlıştır: alışveriş gerçekten
oldu, taksitleri kesildi, ekstreye girdi. Silmek geçmişi yeniden yazar ve
kısmi iadeyi hiç anlatamaz.

İade bu yüzden ayrı bir kayıttır ve **harcamaya bağlıdır**. Harcamanın kendi
taksit planına dokunulmaz; iade, raporlarda ve limit hesabında ayrı bir
alacak kalemi olarak düşülür.

Kart iadesinde `statement_date`, iadenin hangi ekstreye alacak yazılacağını
söyler ve kayıt anında hesaplanıp saklanır. Sonradan kart ayarı değişse bile
yeniden hesaplanmaz; bu, harcamanın anlık görüntü ilkesinin aynısıdır.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_refund_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    refund_date: Mapped[date] = mapped_column(Date, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)

    statement_date: Mapped[date | None] = mapped_column(Date, default=None, index=True)
    """Kart iadesinin alacak yazılacağı ekstre. Nakitte boştur."""

    due_date: Mapped[date | None] = mapped_column(Date, default=None, index=True)
    """Alacağın cebe yansıyacağı tarih: ekstrenin son ödeme günü.

    Ayın nakit durumu son ödeme tarihine göre hesaplandığı için ayrıca
    saklanır; ekstre tarihinden her seferinde yeniden türetmek, kart ayarı
    değişmişse geçmişi yeniden hesaplamak anlamına gelirdi."""

    category_id: Mapped[int] = mapped_column(Integer, index=True)
    """İadenin düşüleceği kategori.

    Harcamanın kategorisinden kopyalanır. Harcama sonradan başka bir
    kategoriye taşınsa bile iade, ait olduğu kategoriden düşülmeye devam
    eder."""

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<Refund {self.amount_minor}kr expense={self.expense_id}>"
