"""Ay sonunda ne kalacak.

Aylık harcama raporu "ne kadar harcadım" sorusunu yanıtlar ve taksitli bir
alışverişi tam tutarıyla gösterir. Bu modül başka bir soruyu yanıtlar: **bu ay
cebimden ne kadar çıkacak.** İkisi aynı değildir; 12 taksitli bir televizyonun
bu aya düşen kısmı yalnızca bir taksittir.

Hesap üç kalemden oluşur:

- Son ödeme tarihi bu aya düşen kredi kartı taksitleri.
- Bu ay yapılmış nakit harcamalar.
- Günü henüz gelmemiş, dolayısıyla kaydı oluşmamış sabit giderler.

Üçüncü kalem olmadan ayın başında bakılan bir tablo fazla iyimser görünürdü:
kira daha kaydedilmemiştir ama ödeneceği kesindir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.installment import STATUS_CANCELLED, STATUS_PAID, ExpenseInstallment
from ..models.payment_method import TYPE_CASH, TYPE_CREDIT_CARD, PaymentMethod
from ..utils.time import month_bounds
from . import income as income_service
from . import recurring, refunds

INACTIVE_STATUSES = (STATUS_PAID, STATUS_CANCELLED)


@dataclass(frozen=True, slots=True)
class MonthlyPosition:
    """Bir ayın nakit durumu."""

    year: int
    month: int
    income_minor: int
    card_due_minor: int
    cash_spent_minor: int
    expected_recurring_minor: int

    @property
    def outflow_minor(self) -> int:
        return self.card_due_minor + self.cash_spent_minor + self.expected_recurring_minor

    @property
    def remaining_minor(self) -> int:
        """Gelirden çıkışlar düşüldükten sonra kalan. Negatif olabilir."""
        return self.income_minor - self.outflow_minor

    @property
    def has_income(self) -> bool:
        return self.income_minor > 0


async def _card_due_in_month(session: AsyncSession, *, start: date, end: date) -> int:
    """Son ödemesi bu aya düşen kredi kartı taksitlerinin toplamı.

    Nakit harcamaların da bir taksit satırı vardır (tek kalem, aynı gün); tür
    filtresi olmadan bu satırlar hem nakit hem kart kaleminde sayılır ve ayın
    çıkışı iki katı görünürdü.
    """
    return await session.scalar(
        select(func.coalesce(func.sum(ExpenseInstallment.amount_minor), 0))
        .join(Expense, ExpenseInstallment.expense_id == Expense.id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.payment_method_type_snapshot == TYPE_CREDIT_CARD,
            ExpenseInstallment.status.not_in(INACTIVE_STATUSES),
            ExpenseInstallment.due_date >= start,
            ExpenseInstallment.due_date <= end,
        )
    )


async def _cash_spent_in_month(session: AsyncSession, *, start: date, end: date) -> int:
    """Nakit harcamalar. Kart harcaması buraya girmez: o, ekstresiyle çıkar."""
    return await session.scalar(
        select(func.coalesce(func.sum(Expense.total_amount_minor), 0)).where(
            Expense.deleted_at.is_(None),
            Expense.payment_method_type_snapshot == TYPE_CASH,
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
    )


async def _expected_recurring(session: AsyncSession, *, today: date) -> int:
    """Bu ay içinde günü henüz gelmemiş nakit sabit giderlerin toplamı.

    Günü geçmiş olanlar zaten kaydedilmiştir ve yukarıdaki kalemlerde
    sayılmıştır; burada tekrar toplanırsa çift sayılırlardı.

    Karta bağlı sabit giderler de bilinçli olarak dışarıda kalır: karta yazılan
    bir abonelik bu ay değil, düştüğü ekstrenin son ödeme tarihinde cepten
    çıkar ve o gün geldiğinde kart kalemi içinde zaten görünür.
    """
    cash_method_ids = set(
        (
            await session.scalars(
                select(PaymentMethod.id).where(PaymentMethod.type == TYPE_CASH)
            )
        ).all()
    )

    total = 0
    for template in await recurring.list_templates(session):
        if template.payment_method_id not in cash_method_ids:
            continue
        when = recurring.scheduled_date(template, year=today.year, month=today.month)
        if when <= today or when < template.start_date:
            continue
        total += template.amount_minor
    return total


async def monthly_position(
    session: AsyncSession, *, today: date
) -> MonthlyPosition:
    """İçinde bulunulan ayın nakit durumunu çıkarır."""
    start, end = month_bounds(today.year, today.month)
    return MonthlyPosition(
        year=today.year,
        month=today.month,
        income_minor=await income_service.monthly_total(
            session, year=today.year, month=today.month
        ),
        # Iade, cikisi azaltir: kart iadesi ekstrenin son odeme gununde,
        # nakit iade ise alindigi gun cebe doner.
        card_due_minor=(
            await _card_due_in_month(session, start=start, end=end)
            - await refunds.card_credit_due_in_month(
                session, year=today.year, month=today.month
            )
        ),
        cash_spent_minor=(
            await _cash_spent_in_month(session, start=start, end=end)
            - await refunds.cash_total_in_month(
                session, year=today.year, month=today.month
            )
        ),
        expected_recurring_minor=await _expected_recurring(session, today=today),
    )
