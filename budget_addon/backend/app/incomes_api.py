"""Gelir uç noktaları.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını
çağırır, sonucu biçimlendirir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.user import User
from .schemas import (
    IncomeCreateIn,
    IncomeOut,
    Money,
)
from .security.identity import current_user
from .services import (
    income as income_service,
)
from .utils.time import local_today

router = APIRouter()


def _income_out(record) -> IncomeOut:
    return IncomeOut(
        id=record.id,
        source=record.source,
        amount=Money.of(record.amount_minor),
        received_date=record.received_date,
        notes=record.notes,
    )


@router.get("/incomes", response_model=list[IncomeOut])
async def read_incomes(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[IncomeOut]:
    today = local_today(settings.timezone)
    records = await income_service.list_incomes(
        session, year=year or today.year, month=month or today.month
    )
    return [_income_out(record) for record in records]


@router.post("/incomes", response_model=IncomeOut, status_code=status.HTTP_201_CREATED)
async def add_income(
    payload: IncomeCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> IncomeOut:
    try:
        record = await income_service.create_income(
            session,
            user=user,
            amount=payload.amount_minor,
            received_date=payload.received_date or local_today(settings.timezone),
            source=payload.source,
            notes=payload.notes,
        )
    except (income_service.IncomeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _income_out(record)


@router.delete("/incomes/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_income(
    income_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    record = await income_service.get_income(session, income_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gelir kaydı bulunamadı")
    await income_service.soft_delete_income(session, user=user, record=record)
