"""Yaklaşan ödemeler takvimi.

Önümüzdeki günlerde ne olacağını tek listede toplar:

- **Sabit giderler**: henüz kaydı üretilmemiş kira, aidat, abonelik.
- **Ekstre kesimi**: kartın o ekstresine şimdiye kadar düşen tutarla.
- **Son ödeme**: kesilmiş veya kesilecek ekstrenin ödenecek tutarı.
- **Birikim hedefi**: tarihi bu aralığa düşen ve henüz tamamlanmamış hedefler.

Hiçbir şey kaydedilmez ve tahmin yürütülmez: her tutar ya bir şablondan ya
da kayıtlı taksitlerden okunur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.payment_method import TYPE_CREDIT_CARD, PaymentMethod
from ..models.savings_goal import SavingsGoal
from . import recurring, reports
from .finance.dates import MONTHS_PER_YEAR
from .finance.statement import due_date_for, first_statement_date

KIND_RECURRING = "recurring"
KIND_STATEMENT = "statement"
KIND_DUE = "card_due"
KIND_GOAL = "savings_goal"

DEFAULT_DAYS = 30
MAX_DAYS = 120


@dataclass(frozen=True, slots=True)
class Event:
    when: date
    kind: str
    title: str
    amount_minor: int | None
    detail: str | None = None
    payment_method_id: int | None = None


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    first = start.year * MONTHS_PER_YEAR + (start.month - 1)
    last = end.year * MONTHS_PER_YEAR + (end.month - 1)
    return [divmod(index, MONTHS_PER_YEAR) for index in range(first, last + 1)]


async def upcoming(
    session: AsyncSession, *, today: date, days: int = DEFAULT_DAYS
) -> list[Event]:
    """Bugünden itibaren `days` gün içindeki olaylar, tarih sırasıyla."""
    days = max(1, min(days, MAX_DAYS))
    until = today + timedelta(days=days)
    events: list[Event] = []

    # Sabit giderler: o ay kaydi henuz uretilmemis olanlar.
    for template in await recurring.list_templates(session):
        for year, month_index in _months_between(today, until):
            month = month_index + 1
            when = recurring.scheduled_date(template, year=year, month=month)
            if when < today or when > until or when < template.start_date:
                continue
            if await recurring._already_generated(session, template, year=year, month=month):
                continue
            events.append(
                Event(
                    when=when,
                    kind=KIND_RECURRING,
                    title=template.name,
                    amount_minor=template.amount_minor,
                    payment_method_id=template.payment_method_id,
                )
            )

    # Ekstreler: kayitli taksitlerden, kart bazinda.
    statements = await reports.upcoming_statements(
        session, since=today - timedelta(days=60), until=until
    )
    totals = {(row.payment_method_id, row.statement_date): row for row in statements}
    for row in statements:
        if today <= row.statement_date <= until:
            events.append(
                Event(
                    when=row.statement_date,
                    kind=KIND_STATEMENT,
                    title=f"{row.payment_method_name} ekstre kesimi",
                    amount_minor=row.total_minor,
                    detail=f"Son ödeme {row.due_date.strftime('%d.%m.%Y')}",
                    payment_method_id=row.payment_method_id,
                )
            )
        if today <= row.due_date <= until:
            events.append(
                Event(
                    when=row.due_date,
                    kind=KIND_DUE,
                    title=f"{row.payment_method_name} son ödeme",
                    amount_minor=row.total_minor,
                    detail=f"Ekstre {row.statement_date.strftime('%d.%m.%Y')}",
                    payment_method_id=row.payment_method_id,
                )
            )

    # Hic taksiti dusmemis bir kartin kesim gunu de gosterilir: kisi o gunu
    # bilmek ister, tutar sifirdir.
    cards = (
        await session.scalars(
            select(PaymentMethod).where(
                PaymentMethod.type == TYPE_CREDIT_CARD,
                PaymentMethod.is_active.is_(True),
                PaymentMethod.statement_day.is_not(None),
            )
        )
    ).all()
    for card in cards:
        if card.statement_day is None:
            continue
        cut = first_statement_date(today, card.statement_day, True)
        if cut <= until and (card.id, cut) not in totals:
            events.append(
                Event(
                    when=cut,
                    kind=KIND_STATEMENT,
                    title=f"{card.name} ekstre kesimi",
                    amount_minor=0,
                    detail=f"Son ödeme {due_date_for(cut, card.due_offset_days).strftime('%d.%m.%Y')}",
                    payment_method_id=card.id,
                )
            )

    goals = (
        await session.scalars(
            select(SavingsGoal).where(
                SavingsGoal.target_date >= today, SavingsGoal.target_date <= until
            )
        )
    ).all()
    for goal in goals:
        remaining = goal.target_minor - goal.saved_minor
        if remaining <= 0:
            continue
        events.append(
            Event(
                when=goal.target_date,
                kind=KIND_GOAL,
                title=f"{goal.name} hedef tarihi",
                amount_minor=remaining,
                detail="Hedefe kalan",
            )
        )

    order = {KIND_DUE: 0, KIND_RECURRING: 1, KIND_STATEMENT: 2, KIND_GOAL: 3}
    events.sort(key=lambda event: (event.when, order[event.kind], event.title))
    return events
