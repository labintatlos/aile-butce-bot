"""Yetkili kullanıcılar (Aykut, Aslıhan)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    ha_user_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=None
    )
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), default=ROLE_MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<User {self.display_name} tg={self.telegram_user_id}>"
