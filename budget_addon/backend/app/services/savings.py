"""Birikim hedefleri.

"Tatil için Haziran'a kadar 50.000 TL" hedefinde asıl soru şudur: **bundan
sonra her ay ne kadar kenara ayırmalıyım ve bu ayki bütçem buna yetiyor mu?**

Hesap tamamen deterministiktir:

1. Kalan = hedef − biriken (eksiye düşmez).
2. Kalan ay = bu ay ile hedef tarihin ayı arasındaki ay sayısı, **bu ay
   dahil**. Ekimde Haziran sonu hedefi için 9 aydır (Eki…Haz). Ayın kaçı
   olduğu önemsizdir: bu ay da bir birikim ayıdır.
3. Aylık gereken = kalan ÷ kalan ay, kuruşa **yukarı** yuvarlanır. Aşağı
   yuvarlansaydı son ay birkaç kuruş eksik kalırdı.
4. Hedef tarihi geçmiş ve tamamlanmamış hedef "süresi geçti" sayılır; aylık
   toplamlara girmez, çünkü ona "ayda şu kadar" demek anlamsızdır.

Bu ayın gereksinimi, ayın nakit durumunda kalan tutarla karşılaştırılır
(`cashflow.monthly_position`: gelir − kart ödemesi − nakit harcama − günü
gelmemiş sabit giderler). Gelir girilmemişse karşılaştırma yapılmaz; sıfır
gelirle "yetmiyor" demek yanıltıcı olurdu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import ACTION_CREATE, ACTION_DELETE, ACTION_UPDATE
from ..models.savings_goal import SavingsGoal
from ..models.user import User
from . import cashflow
from .audit import record_audit

ENTITY_SAVINGS_GOAL = "savings_goal"
NAME_MAX_LENGTH = 80


class SavingsError(Exception):
    """Kullanıcıya gösterilebilir hata."""


def months_left(today: date, target_date: date) -> int:
    """Bu ay dahil, hedef ayına kadar kalan ay sayısı. Hedef geçtiyse sıfır."""
    if target_date < today:
        return 0
    return (target_date.year * 12 + target_date.month) - (today.year * 12 + today.month) + 1


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


@dataclass(frozen=True, slots=True)
class GoalStatus:
    id: int
    name: str
    target_minor: int
    saved_minor: int
    target_date: date
    months_left: int

    @property
    def remaining_minor(self) -> int:
        return max(self.target_minor - self.saved_minor, 0)

    @property
    def is_complete(self) -> bool:
        return self.saved_minor >= self.target_minor

    @property
    def is_overdue(self) -> bool:
        return not self.is_complete and self.months_left == 0

    @property
    def monthly_required_minor(self) -> int:
        """Hedefe zamanında ulaşmak için bu aydan itibaren her ay ayrılacak tutar."""
        if self.is_complete or self.months_left == 0:
            return 0
        return _ceil_div(self.remaining_minor, self.months_left)

    @property
    def ratio(self) -> int:
        """Biriken yüzde; 100'de durur."""
        return min(self.saved_minor * 100 // self.target_minor, 100)


@dataclass(frozen=True, slots=True)
class SavingsOverview:
    goals: list[GoalStatus]
    month_remaining_minor: int | None
    """Bu ayın nakit durumunda kalan; gelir girilmemişse `None`."""

    @property
    def monthly_required_minor(self) -> int:
        return sum(goal.monthly_required_minor for goal in self.goals)

    @property
    def covers(self) -> bool | None:
        """Bu ayın kalanı, hedeflerin bu ay gerektirdiğini karşılıyor mu?"""
        if self.month_remaining_minor is None or self.monthly_required_minor == 0:
            return None
        return self.month_remaining_minor >= self.monthly_required_minor


def status_of(goal: SavingsGoal, *, today: date) -> GoalStatus:
    return GoalStatus(
        id=goal.id,
        name=goal.name,
        target_minor=goal.target_minor,
        saved_minor=goal.saved_minor,
        target_date=goal.target_date,
        months_left=months_left(today, goal.target_date),
    )


async def overview(session: AsyncSession, *, today: date) -> SavingsOverview:
    goals = (
        await session.scalars(
            select(SavingsGoal).order_by(SavingsGoal.target_date, SavingsGoal.id)
        )
    ).all()
    position = await cashflow.monthly_position(session, today=today)
    return SavingsOverview(
        goals=[status_of(goal, today=today) for goal in goals],
        month_remaining_minor=position.remaining_minor if position.has_income else None,
    )


def _clean_name(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise SavingsError("Hedefin adı boş olamaz")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise SavingsError(f"Hedefin adı en fazla {NAME_MAX_LENGTH} karakter olabilir")
    return cleaned


def _check_target(target_minor: int) -> None:
    if target_minor <= 0:
        raise SavingsError("Hedef tutar sıfırdan büyük olmalıdır")


def _snapshot(goal: SavingsGoal) -> dict[str, object]:
    return {
        "name": goal.name,
        "target_minor": goal.target_minor,
        "saved_minor": goal.saved_minor,
        "target_date": goal.target_date,
    }


async def get_goal(session: AsyncSession, goal_id: int) -> SavingsGoal:
    goal = await session.get(SavingsGoal, goal_id)
    if goal is None:
        raise SavingsError("Birikim hedefi bulunamadı")
    return goal


async def create_goal(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    target_minor: int,
    target_date: date,
    today: date,
    saved_minor: int = 0,
) -> SavingsGoal:
    _check_target(target_minor)
    if target_date < today:
        raise SavingsError("Hedef tarih geçmişte olamaz")
    if saved_minor < 0:
        raise SavingsError("Biriken tutar negatif olamaz")
    goal = SavingsGoal(
        name=_clean_name(name),
        target_minor=target_minor,
        saved_minor=saved_minor,
        target_date=target_date,
        created_by_user_id=user.id,
    )
    try:
        session.add(goal)
        await session.flush()
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_SAVINGS_GOAL,
            entity_id=goal.id,
            action=ACTION_CREATE,
            new_data=_snapshot(goal),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return goal


async def update_goal(
    session: AsyncSession,
    *,
    user: User,
    goal: SavingsGoal,
    name: str | None = None,
    target_minor: int | None = None,
    target_date: date | None = None,
) -> SavingsGoal:
    before = _snapshot(goal)
    if name is not None:
        goal.name = _clean_name(name)
    if target_minor is not None:
        _check_target(target_minor)
        goal.target_minor = target_minor
    if target_date is not None:
        goal.target_date = target_date
    await _commit_change(session, user=user, goal=goal, before=before)
    return goal


async def add_to_goal(
    session: AsyncSession, *, user: User, goal: SavingsGoal, amount_minor: int
) -> SavingsGoal:
    """Biriken tutara ekler; eksi tutar kenardan para alındığı anlamına gelir."""
    if amount_minor == 0:
        raise SavingsError("Tutar sıfır olamaz")
    if goal.saved_minor + amount_minor < 0:
        raise SavingsError("Biriken tutardan fazlası çekilemez")
    before = _snapshot(goal)
    goal.saved_minor += amount_minor
    await _commit_change(session, user=user, goal=goal, before=before)
    return goal


async def delete_goal(session: AsyncSession, *, user: User, goal: SavingsGoal) -> None:
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_SAVINGS_GOAL,
            entity_id=goal.id,
            action=ACTION_DELETE,
            old_data=_snapshot(goal),
        )
        await session.delete(goal)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def _commit_change(
    session: AsyncSession, *, user: User, goal: SavingsGoal, before: dict[str, object]
) -> None:
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_SAVINGS_GOAL,
            entity_id=goal.id,
            action=ACTION_UPDATE,
            old_data=before,
            new_data=_snapshot(goal),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
