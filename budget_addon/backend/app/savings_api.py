"""Birikim hedefi uç noktaları.

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
    Money,
    SavingsDepositIn,
    SavingsGoalCreateIn,
    SavingsGoalOut,
    SavingsGoalUpdateIn,
    SavingsOverviewOut,
)
from .security.identity import current_user
from .services import savings
from .utils.time import local_today

router = APIRouter()


def _goal_out(goal: savings.GoalStatus) -> SavingsGoalOut:
    return SavingsGoalOut(
        id=goal.id,
        name=goal.name,
        target=Money.of(goal.target_minor),
        saved=Money.of(goal.saved_minor),
        remaining=Money.of(goal.remaining_minor),
        target_date=goal.target_date,
        months_left=goal.months_left,
        monthly_required=Money.of(goal.monthly_required_minor),
        ratio=goal.ratio,
        is_complete=goal.is_complete,
        is_overdue=goal.is_overdue,
    )


async def _overview(session: AsyncSession, settings: Settings) -> SavingsOverviewOut:
    report = await savings.overview(session, today=local_today(settings.timezone))
    return SavingsOverviewOut(
        goals=[_goal_out(goal) for goal in report.goals],
        monthly_required=Money.of(report.monthly_required_minor),
        month_remaining=(
            Money.of(report.month_remaining_minor)
            if report.month_remaining_minor is not None
            else None
        ),
        covers=report.covers,
    )


async def _goal_or_404(session: AsyncSession, goal_id: int):
    try:
        return await savings.get_goal(session, goal_id)
    except savings.SavingsError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/savings-goals", response_model=SavingsOverviewOut)
async def read_savings_goals(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SavingsOverviewOut:
    """Hedefler, aylık gereken tutar ve bu ayın kalanıyla karşılaştırma."""
    return await _overview(session, settings)


@router.post(
    "/savings-goals", response_model=SavingsOverviewOut, status_code=status.HTTP_201_CREATED
)
async def add_savings_goal(
    payload: SavingsGoalCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SavingsOverviewOut:
    try:
        await savings.create_goal(
            session,
            user=user,
            name=payload.name,
            target_minor=payload.target_minor,
            target_date=payload.target_date,
            saved_minor=payload.saved_minor,
            today=local_today(settings.timezone),
        )
    except savings.SavingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _overview(session, settings)


@router.patch("/savings-goals/{goal_id}", response_model=SavingsOverviewOut)
async def edit_savings_goal(
    goal_id: int,
    payload: SavingsGoalUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SavingsOverviewOut:
    goal = await _goal_or_404(session, goal_id)
    try:
        await savings.update_goal(
            session,
            user=user,
            goal=goal,
            name=payload.name,
            target_minor=payload.target_minor,
            target_date=payload.target_date,
        )
    except savings.SavingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _overview(session, settings)


@router.post("/savings-goals/{goal_id}/deposits", response_model=SavingsOverviewOut)
async def deposit_to_savings_goal(
    goal_id: int,
    payload: SavingsDepositIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SavingsOverviewOut:
    """Biriken tutara ekler ya da (eksi tutarla) birikimden alır."""
    goal = await _goal_or_404(session, goal_id)
    try:
        await savings.add_to_goal(session, user=user, goal=goal, amount_minor=payload.amount_minor)
    except savings.SavingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _overview(session, settings)


@router.delete("/savings-goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_savings_goal(
    goal_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    goal = await _goal_or_404(session, goal_id)
    await savings.delete_goal(session, user=user, goal=goal)
