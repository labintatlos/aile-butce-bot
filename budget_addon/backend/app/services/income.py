"""Gelir kayıtlarının yaşam döngüsü.

Harcama tarafındaki ilkelerin aynısı geçerlidir: tutar kuruş cinsinden tam
sayıdır, silme yumuşaktır ve her değişiklik denetim kaydına düşer.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import ACTION_CREATE, ACTION_DELETE
from ..models.base import utc_now
from ..models.income import Income
from ..models.user import User
from ..utils.time import month_bounds
from .audit import record_audit
from .finance.money import parse_amount_to_minor

ENTITY_INCOME = "income"

DEFAULT_SOURCE = "Gelir"


class IncomeError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


def _snapshot(record: Income) -> dict[str, object]:
    return {
        "amount_minor": record.amount_minor,
        "received_date": record.received_date,
        "source": record.source,
    }


async def create_income(
    session: AsyncSession,
    *,
    user: User,
    amount: str | int,
    received_date: date,
    source: str = DEFAULT_SOURCE,
    notes: str | None = None,
) -> Income:
    amount_minor = parse_amount_to_minor(amount)
    source = source.strip() or DEFAULT_SOURCE

    record = Income(
        created_by_user_id=user.id,
        received_date=received_date,
        amount_minor=amount_minor,
        source=source,
        notes=notes,
    )
    try:
        session.add(record)
        await session.flush()
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_INCOME,
            entity_id=record.id,
            action=ACTION_CREATE,
            new_data=_snapshot(record),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return record


async def soft_delete_income(
    session: AsyncSession, *, user: User, record: Income
) -> None:
    """Geliri raporlardan çıkarır, satırı silmez."""
    if record.deleted_at is not None:
        return
    record.deleted_at = utc_now()
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_INCOME,
            entity_id=record.id,
            action=ACTION_DELETE,
            old_data=_snapshot(record),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def get_income(session: AsyncSession, income_id: int) -> Income | None:
    return await session.scalar(
        select(Income).where(Income.id == income_id, Income.deleted_at.is_(None))
    )


async def list_incomes(
    session: AsyncSession, *, year: int, month: int
) -> list[Income]:
    start, end = month_bounds(year, month)
    return list(
        (
            await session.scalars(
                select(Income)
                .where(
                    Income.deleted_at.is_(None),
                    Income.received_date >= start,
                    Income.received_date <= end,
                )
                .order_by(Income.received_date, Income.id)
            )
        ).all()
    )


async def monthly_total(session: AsyncSession, *, year: int, month: int) -> int:
    start, end = month_bounds(year, month)
    return await session.scalar(
        select(func.coalesce(func.sum(Income.amount_minor), 0)).where(
            Income.deleted_at.is_(None),
            Income.received_date >= start,
            Income.received_date <= end,
        )
    )
