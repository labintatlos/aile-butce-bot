"""Denetim kaydı yazımı.

Kayıtlar harcama işlemiyle **aynı transaction** içinde yazılır: işlem geri
alınırsa denetim kaydı da geri alınır, böylece gerçekleşmemiş bir değişiklik
loglanmış görünmez.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import AuditLog

_SENSITIVE_KEYS = {"token", "init_data", "authorization", "password", "secret"}


def _serialise(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    cleaned = {
        key: value
        for key, value in payload.items()
        if not any(marker in key.lower() for marker in _SENSITIVE_KEYS)
    }
    return json.dumps(cleaned, ensure_ascii=False, default=str, sort_keys=True)


def record_audit(
    session: AsyncSession,
    *,
    user_id: int | None,
    entity_type: str,
    entity_id: int,
    action: str,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_data=_serialise(old_data),
        new_data=_serialise(new_data),
    )
    session.add(entry)
    return entry
