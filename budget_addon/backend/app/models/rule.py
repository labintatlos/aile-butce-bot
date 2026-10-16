"""Otomatik kural: "açıklamada X geçiyorsa şunu yap".

Kural deterministik bir metin eşleşmesidir; dil modeli veya bulanık
benzerlik kullanılmaz. Karşılaştırmadan önce iki taraf da sadeleştirilir
(Türkçe karakter ve büyük/küçük harf farkı yok sayılır, `#etiket`ler
çıkarılır), böylece "MIGROS", "Migros" ve "migros #tatil" aynı kurala uyar.

Kural kendiliğinden kayıt **yapmaz**. Formda kategoriyi önerir, içe
aktarmada önizlemeyi doldurur; son söz her zaman kullanıcınındır.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

MATCH_CONTAINS = "contains"
MATCH_EQUALS = "equals"
MATCH_STARTS_WITH = "starts_with"
MATCH_TYPES = (MATCH_CONTAINS, MATCH_EQUALS, MATCH_STARTS_WITH)


class Rule(TimestampMixin, Base):
    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint(
            "match_type IN ('contains', 'equals', 'starts_with')",
            name="ck_rule_match_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(120))
    """Sadeleştirilmiş hâliyle saklanan arama metni."""
    match_type: Mapped[str] = mapped_column(String(16), default=MATCH_CONTAINS)

    set_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), default=None, index=True
    )
    set_payment_method_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="SET NULL"), default=None
    )
    set_description: Mapped[str | None] = mapped_column(String(120), default=None)
    """Açıklamayı bu metne çevirir ("MIGROS 1234 ISTANBUL" → "Migros").

    Etiketler korunur: `#tatil` yazılmış bir harcama yeniden adlandırılınca
    etiketini kaybetmez."""

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    """Küçük olan önce denenir. Bir alanı ilk dolduran kural kazanır."""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rule {self.match_type} {self.pattern!r}>"
