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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=utc_now,
    )
