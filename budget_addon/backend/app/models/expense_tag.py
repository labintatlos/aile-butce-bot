"""Harcama etiketleri.

Kategori "bu para neye gitti" sorusunu yanıtlar ve sabittir. Etiket başka bir
soruyu yanıtlar: "Bodrum tatili toplam ne tuttu?" Aynı tatilin benzini,
marketi, restoranı farklı kategorilerdedir ama tek bir olaya aittir.

Etiket ayrı bir alan değildir; açıklamanın içine `#tatil` diye yazılır ve
buraya çıkarılır. Böylece hızlı giriş bozulmaz, öğrenilecek yeni bir söz
dizimi olmaz.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

MAX_TAG_LENGTH = 32


class ExpenseTag(Base):
    __tablename__ = "expense_tags"
    __table_args__ = (
        UniqueConstraint("expense_id", "tag", name="uq_expense_tag"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    tag: Mapped[str] = mapped_column(String(MAX_TAG_LENGTH), index=True)
    """Küçük harfe ve ASCII'ye indirgenmiş etiket.

    `#Tatil`, `#tatil` ve `#TATİL` aynı etikettir: kullanıcı aynı şeyi iki
    farklı toplamda görmemelidir."""

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<ExpenseTag #{self.tag} expense={self.expense_id}>"
