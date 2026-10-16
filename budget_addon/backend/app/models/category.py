"""Harcama kategorileri."""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    emoji: Mapped[str] = mapped_column(String(8), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_budget_minor: Mapped[int | None] = mapped_column(
        BigInteger, default=None
    )
    """Bu kategori için aylık harcama hedefi, kuruş cinsinden.

    Boş bırakılabilir: hedefi olmayan kategori hiçbir uyarı üretmez ve
    raporda yalnızca tutarıyla görünür. Hedef bir sınır değil ölçüdür;
    aşıldığında harcama kaydı engellenmez, yalnızca haber verilir."""

    group_name: Mapped[str | None] = mapped_column(String(64), default=None)
    """Kategorinin bağlı olduğu üst grup ("Ev", "Ulaşım" gibi).

    Ayrı bir tablo yerine düz metindir: grubun adından başka bir özelliği
    yoktur ve aynı adı taşıyan kategoriler raporda bir arada toplanır. Boş
    bırakılan kategori "Diğer" altında görünür."""

    rollover: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    """Ay içinde harcanmayan hedef bir sonraki aya devreder mi.

    Açıkken aşılan tutar da devreder: geçen ay 500 TL fazla harcanan
    kategorinin bu ayki hedefi 500 TL eksik başlar. Ayrıntı için bkz.
    `services/budgets.py`."""

    rollover_since: Mapped[date | None] = mapped_column(Date, default=None)
    """Devretmenin başladığı ayın ilk günü.

    Devir bu aydan itibaren biriktirilir; daha önceki aylar hesaba katılmaz.
    Böylece devri açan kişi yıllar öncesinin farkını bir anda karşısında
    bulmaz."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name}>"
