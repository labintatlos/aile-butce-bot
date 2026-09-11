"""Kişisel yıllık bütçeler.

Her kişinin ortak (ev) giderinden bağımsız, yıllık bir kişisel harcama hakkı
vardır. Kişisel işaretlenen harcama, **kimin kartıyla alındığına bakılmaksızın**
sahibinin bütçesinden düşer ve ortak gider toplamlarına dahil olmaz.

Taksitli kişisel alışverişin tamamı alışveriş tarihinde bütçeden düşer: bütçe
"bu yıl kendime ne kadar harcadım" sorusunu yanıtlar, kart ödemesini değil.
İadeler, alındıkları yılın bütçesine geri eklenir.

Yıl sonunda artan tutar devretmez; her yıl belirlenen tutarla başlar.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.personal_budget import PersonalBudget
from ..models.refund import Refund
from ..models.user import User


class PersonalBudgetError(Exception):
    """Kullanıcıya gösterilebilir hata."""


@dataclass(frozen=True, slots=True)
class PersonalBudgetStatus:
    user_id: int
    name: str
    year: int
    budget_minor: int | None
    spent_minor: int
    expense_count: int
    year_elapsed_ratio: int
    """Yılın yüzde kaçı geçti; harcama hızını kıyaslamak için."""

    @property
    def remaining_minor(self) -> int | None:
        if self.budget_minor is None:
            return None
        return self.budget_minor - self.spent_minor

    @property
    def ratio(self) -> int:
        if not self.budget_minor:
            return 0
        return round(self.spent_minor * 100 / self.budget_minor)

    @property
    def is_exceeded(self) -> bool:
        return self.budget_minor is not None and self.spent_minor > self.budget_minor


def _elapsed_ratio(year: int, today: date) -> int:
    if today.year < year:
        return 0
    if today.year > year:
        return 100
    days = 366 if calendar.isleap(year) else 365
    return round(today.timetuple().tm_yday * 100 / days)


async def yearly_status(
    session: AsyncSession, *, year: int, today: date
) -> list[PersonalBudgetStatus]:
    """Etkin kişilerin o yılki kişisel bütçe durumunu verir."""
    start, end = date(year, 1, 1), date(year, 12, 31)

    people = (
        await session.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.id)
        )
    ).all()

    budgets = dict(
        (
            await session.execute(
                select(PersonalBudget.user_id, PersonalBudget.amount_minor).where(
                    PersonalBudget.year == year
                )
            )
        ).all()
    )

    spent = {
        row.owner: (row.total, row.count)
        for row in (
            await session.execute(
                select(
                    Expense.owner_user_id.label("owner"),
                    func.coalesce(func.sum(Expense.total_amount_minor), 0).label("total"),
                    func.count(Expense.id).label("count"),
                )
                .where(
                    Expense.deleted_at.is_(None),
                    Expense.owner_user_id.is_not(None),
                    Expense.transaction_date >= start,
                    Expense.transaction_date <= end,
                )
                .group_by(Expense.owner_user_id)
            )
        ).all()
    }

    refunded = dict(
        (
            await session.execute(
                select(Expense.owner_user_id, func.coalesce(func.sum(Refund.amount_minor), 0))
                .join(Expense, Refund.expense_id == Expense.id)
                .where(
                    Refund.deleted_at.is_(None),
                    Expense.deleted_at.is_(None),
                    Expense.owner_user_id.is_not(None),
                    Refund.refund_date >= start,
                    Refund.refund_date <= end,
                )
                .group_by(Expense.owner_user_id)
            )
        ).all()
    )

    elapsed = _elapsed_ratio(year, today)
    result = []
    for person in people:
        total, count = spent.get(person.id, (0, 0))
        result.append(
            PersonalBudgetStatus(
                user_id=person.id,
                name=person.display_name,
                year=year,
                budget_minor=budgets.get(person.id),
                spent_minor=total - refunded.get(person.id, 0),
                expense_count=count,
                year_elapsed_ratio=elapsed,
            )
        )
    return result


async def set_budget(
    session: AsyncSession, *, user_id: int, year: int, amount_minor: int | None
) -> None:
    """Bir kişinin o yılki bütçesini yazar; `None` bütçeyi kaldırır."""
    person = await session.get(User, user_id)
    if person is None:
        raise PersonalBudgetError("Kişi bulunamadı")
    if amount_minor is not None and amount_minor < 0:
        raise PersonalBudgetError("Bütçe negatif olamaz")

    existing = await session.scalar(
        select(PersonalBudget).where(
            PersonalBudget.user_id == user_id, PersonalBudget.year == year
        )
    )
    if amount_minor is None:
        if existing is not None:
            await session.delete(existing)
    elif existing is None:
        session.add(PersonalBudget(user_id=user_id, year=year, amount_minor=amount_minor))
    else:
        existing.amount_minor = amount_minor
    await session.commit()
