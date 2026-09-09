"""Gönderilmiş hatırlatmaların kaydı.

Eklenti gün içinde yeniden başlatılabilir ve zamanlayıcı dakikada bir uyanır.
Aynı hatırlatmanın iki kez gönderilmemesi için her gönderim burada
işaretlenir; işaret kalıcıdır, yani yeniden başlatma tekrarlı bildirime yol
açmaz.

`reference`, hatırlatmayı benzersiz kılan her şeyi taşır: kime gönderildiği,
hangi tarihe ait olduğu ve varsa hangi kart. Böylece tek bir tabloyla her
hatırlatma türü tekilleştirilebilir.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utc_now


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        UniqueConstraint("kind", "reference", name="uq_notification_kind_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    reference: Mapped[str] = mapped_column(String(96))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - hata ayiklama kolayligi
        return f"<NotificationLog {self.kind} {self.reference}>"
