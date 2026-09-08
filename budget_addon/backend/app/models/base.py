"""ORM temel sınıfları ve ortak sütun tipleri.

Para sütunları `BigInteger` ve **kuruş** cinsindendir. Şemada `Float`/`Numeric`
kullanılmaz; gerekçesi docs/FINANCE_RULES.md bölüm 1'de.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MoneyMinor = Annotated[int, mapped_column(BigInteger)]
"""Kuruş cinsinden tam sayı tutar."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Tüm modellerin ortak tabanı."""


class TimestampMixin:
    """Oluşturulma ve güncellenme zamanları.

    Değer hem Python tarafında (`default`) hem veritabanı tarafında
    (`server_default`) üretilir. İkisi de gereklidir: `server_default` şemayı
    Alembic göçü kurduğunda tablo tanımına yazılmak zorundadır ve bir göçte
    atlanırsa kayıt eklenemez hâle gelir. Python tarafındaki `default` bu tür
    bir şema kaymasında da doğru değeri sağlar.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )
