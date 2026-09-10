"""Denetim kaydı.

Kim, neyi, ne zaman değiştirdi. `old_data` ve `new_data` JSON metnidir; içine
şifre, oturum çerezi veya başka kimlik doğrulama verisi asla yazılmaz.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTION_RESTORE = "restore"
AUDIT_ACTIONS = (ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE, ACTION_RESTORE)

ENTITY_EXPENSE = "expense"
ENTITY_PAYMENT_METHOD = "payment_method"
ENTITY_CATEGORY = "category"
ENTITY_USER = "user"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete', 'restore')", name="ck_audit_action"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(16))
    old_data: Mapped[str | None] = mapped_column(Text, default=None)
    new_data: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.action} {self.entity_type}#{self.entity_id}>"
