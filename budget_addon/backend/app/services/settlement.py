"""Ortak giderlerin denkleştirilmesi.

İki kişilik bir bütçede harcamaların çoğu ortaktır ama ödeyen her seferinde
aynı kişi olmaz. Ay sonunda sorulan soru basittir: kim kime ne kadar borçlu?

Hesap yalnızca **ortak** işaretli harcamaları kapsar. Kişisel bir harcama
raporlarda görünür ama denkleştirmeye girmez; kimsenin kimseden yarısını
istemesi beklenmez.

Ödeyen, kaydı giren kişidir. İki kişilik bir kurulumda kaydı kim girdiyse
parayı da o vermiştir; ayrı bir "ödeyen" alanı, her girişte doldurulacak
gereksiz bir soru olurdu.

Kuruş kaybı olmaz: pay, `split_minor` ile bölünür ve payların toplamı her
zaman ortak toplama eşittir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.user import User
from ..utils.time import month_bounds
from . import refunds
from .finance.money import split_minor


@dataclass(frozen=True, slots=True)
class PersonBalance:
    """Bir kişinin ortak gidere katkısı ve payı."""

    user_id: int
    name: str
    paid_minor: int
    share_minor: int

    @property
    def balance_minor(self) -> int:
        """Artı ise alacaklı, eksi ise borçludur."""
        return self.paid_minor - self.share_minor


@dataclass(frozen=True, slots=True)
class Settlement:
    """Bir ayın denkleştirme tablosu."""

    year: int
    month: int
    shared_total_minor: int
    balances: list[PersonBalance] = field(default_factory=list)

    @property
    def is_even(self) -> bool:
        return all(person.balance_minor == 0 for person in self.balances)

    @property
    def creditor(self) -> PersonBalance | None:
        """En çok alacaklı kişi. Denkse `None`."""
        if self.is_even or not self.balances:
            return None
        return max(self.balances, key=lambda person: person.balance_minor)

    @property
    def debtor(self) -> PersonBalance | None:
        if self.is_even or not self.balances:
            return None
        return min(self.balances, key=lambda person: person.balance_minor)

    @property
    def transfer_minor(self) -> int:
        """Borçlunun alacaklıya vermesi gereken tutar."""
        creditor = self.creditor
        return creditor.balance_minor if creditor is not None else 0


async def monthly_settlement(
    session: AsyncSession, *, year: int, month: int
) -> Settlement:
    """Ortak giderleri kişilere böler ve dengeyi çıkarır."""
    start, end = month_bounds(year, month)
    shared = (
        Expense.deleted_at.is_(None),
        Expense.is_shared.is_(True),
        Expense.transaction_date >= start,
        Expense.transaction_date <= end,
    )

    paid_by = dict(
        (
            await session.execute(
                select(
                    Expense.created_by_user_id,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0),
                )
                .where(*shared)
                .group_by(Expense.created_by_user_id)
            )
        ).all()
    )

    # Iade, odeyene geri doner: ortak gidere katkisini o kadar azaltir.
    refunded_by = dict(
        (
            await session.execute(
                select(
                    Expense.created_by_user_id,
                    func.coalesce(func.sum(refunds.Refund.amount_minor), 0),
                )
                .join(refunds.Refund, refunds.Refund.expense_id == Expense.id)
                .where(
                    *shared,
                    refunds.Refund.deleted_at.is_(None),
                    refunds.Refund.refund_date >= start,
                    refunds.Refund.refund_date <= end,
                )
                .group_by(Expense.created_by_user_id)
            )
        ).all()
    )

    people = list(
        (
            await session.scalars(
                select(User).where(User.is_active.is_(True)).order_by(User.id)
            )
        ).all()
    )
    if not people:
        return Settlement(year=year, month=month, shared_total_minor=0)

    contributions = {
        person.id: paid_by.get(person.id, 0) - refunded_by.get(person.id, 0)
        for person in people
    }
    total = sum(contributions.values())
    shares = split_minor(total, len(people)) if total > 0 else [0] * len(people)

    return Settlement(
        year=year,
        month=month,
        shared_total_minor=total,
        balances=[
            PersonBalance(
                user_id=person.id,
                name=person.display_name,
                paid_minor=contributions[person.id],
                share_minor=share,
            )
            for person, share in zip(people, shares)
        ],
    )
