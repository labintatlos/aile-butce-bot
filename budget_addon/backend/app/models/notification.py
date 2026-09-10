"""Site içi bildirimler ve anlık bildirim abonelikleri.

Bildirim önce burada saklanır; e-posta ve telefondaki anlık bildirim bu kaydın
kopyasıdır. Dış kanal o an çalışmasa bile bildirim sitede kaybolmaz.

Anlık bildirim aboneliği cihaza aittir: aynı kişi telefonda ve bilgisayarda
ayrı ayrı açabilir. Tarayıcının verdiği adres (`endpoint`) benzersizdir; aynı
cihazda başka biri giriş yapıp açarsa abonelik ona geçer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utc_now


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    link: Mapped[str | None] = mapped_column(String(64), default=None)
    """Arayüzde açılacak sayfa (ör. `raporlar`)."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<Notification {self.kind} user={self.user_id}>"


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
