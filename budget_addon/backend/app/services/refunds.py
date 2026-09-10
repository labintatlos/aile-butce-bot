"""İadeler: tam veya kısmi para iadesi.

Silmek yerine iade kaydı tutmanın üç nedeni var: alışveriş gerçekten oldu ve
taksitleri ekstreye girdi; kısmi iade silmeyle hiç anlatılamaz; geçmişi
yeniden yazmak bu sistemin temel ilkesine aykırıdır.

İade harcamanın taksit planına dokunmaz. Raporlarda ayrı bir alacak kalemi
olarak düşülür: aylık harcama netleşir, kategori bütçesi rahatlar, kartın
bağlı limiti serbest kalır ve ayın nakit çıkışı azalır.

Bir harcamadan toplam iade, harcamanın tutarını **aşamaz**. Aşabilseydi
kategori toplamı negatife düşer ve rapor anlamını yitirirdi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import ACTION_CREATE, ACTION_DELETE
from ..models.base import utc_now
from ..models.expense import Expense
from ..models.payment_method import TYPE_CREDIT_CARD
from ..models.refund import Refund
from ..models.user import User
from ..utils.time import month_bounds
from .audit import record_audit
from .finance.money import parse_amount_to_minor
from .finance.statement import due_date_for, first_statement_date
from .expenses import get_expense

ENTITY_REFUND = "refund"


class RefundError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


def _live() -> tuple:
    return (Refund.deleted_at.is_(None),)


def _snapshot(refund: Refund) -> dict[str, object]:
    return {
        "expense_id": refund.expense_id,
        "amount_minor": refund.amount_minor,
        "refund_date": refund.refund_date,
        "statement_date": refund.statement_date,
        "due_date": refund.due_date,
    }


async def refunded_total(session: AsyncSession, expense_id: int) -> int:
    """Bir harcamadan bugüne kadar iade edilen toplam."""
    return await session.scalar(
        select(func.coalesce(func.sum(Refund.amount_minor), 0)).where(
            Refund.expense_id == expense_id, *_live()
        )
    )


def _statement_date_for(expense: Expense, refund_date: date) -> date | None:
    """Kart iadesinin hangi ekstreye alacak yazılacağı.

    Harcamanın anlık görüntüsündeki kesim günü kullanılır: iade, aynı kartın
    aynı koşullarına tabidir. Nakit harcamada ekstre kavramı yoktur.
    """
    if expense.payment_method_type_snapshot != TYPE_CREDIT_CARD:
        return None
    if expense.statement_day_snapshot is None:
        return None
    return first_statement_date(
        refund_date,
        expense.statement_day_snapshot,
        bool(expense.cutoff_inclusive_snapshot),
    )


async def create_refund(
    session: AsyncSession,
    *,
    user: User,
    expense_id: int,
    amount: str | int,
    refund_date: date,
    notes: str | None = None,
) -> Refund:
    """İadeyi kaydeder. Harcamanın taksit planına dokunulmaz."""
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise RefundError("Harcama bulunamadı")

    amount_minor = parse_amount_to_minor(amount)
    already = await refunded_total(session, expense_id)
    if already + amount_minor > expense.total_amount_minor:
        remaining = expense.total_amount_minor - already
        raise RefundError(
            "İade tutarı harcamayı aşamaz. "
            f"Bu harcamadan iade edilebilecek kalan: {remaining / 100:.2f} TL"
        )

    statement_date = _statement_date_for(expense, refund_date)
    refund = Refund(
        expense_id=expense.id,
        created_by_user_id=user.id,
        refund_date=refund_date,
        amount_minor=amount_minor,
        statement_date=statement_date,
        due_date=(
            due_date_for(statement_date, expense.due_offset_days_snapshot or 10)
            if statement_date is not None
            else None
        ),
        category_id=expense.category_id,
        notes=notes,
    )
    try:
        session.add(refund)
        await session.flush()
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_REFUND,
            entity_id=refund.id,
            action=ACTION_CREATE,
            new_data=_snapshot(refund),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return refund


async def soft_delete_refund(
    session: AsyncSession, *, user: User, refund: Refund
) -> None:
    if refund.deleted_at is not None:
        return
    refund.deleted_at = utc_now()
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_REFUND,
            entity_id=refund.id,
            action=ACTION_DELETE,
            old_data=_snapshot(refund),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def get_refund(session: AsyncSession, refund_id: int) -> Refund | None:
    return await session.scalar(
        select(Refund).where(Refund.id == refund_id, *_live())
    )


async def list_for_expense(session: AsyncSession, expense_id: int) -> list[Refund]:
    return list(
        (
            await session.scalars(
                select(Refund)
                .where(Refund.expense_id == expense_id, *_live())
                .order_by(Refund.refund_date, Refund.id)
            )
        ).all()
    )


# ---------------------------------------------------------------------------
# Raporlara giren toplamlar
# ---------------------------------------------------------------------------


async def total_in_month(session: AsyncSession, *, year: int, month: int) -> int:
    """Bir ayda alınan iadelerin toplamı."""
    start, end = month_bounds(year, month)
    return await session.scalar(
        select(func.coalesce(func.sum(Refund.amount_minor), 0)).where(
            Refund.refund_date >= start, Refund.refund_date <= end, *_live()
        )
    )


async def by_category_in_month(
    session: AsyncSession, *, year: int, month: int
) -> dict[int, int]:
    """Kategori kimliğine göre ay içindeki iade toplamları."""
    start, end = month_bounds(year, month)
    rows = await session.execute(
        select(Refund.category_id, func.coalesce(func.sum(Refund.amount_minor), 0))
        .where(Refund.refund_date >= start, Refund.refund_date <= end, *_live())
        .group_by(Refund.category_id)
    )
    return dict(rows.all())


async def cash_total_in_month(
    session: AsyncSession, *, year: int, month: int
) -> int:
    """Nakit harcamalardan ay içinde geri alınan tutar."""
    start, end = month_bounds(year, month)
    return await session.scalar(
        select(func.coalesce(func.sum(Refund.amount_minor), 0))
        .join(Expense, Refund.expense_id == Expense.id)
        .where(
            Expense.payment_method_type_snapshot != TYPE_CREDIT_CARD,
            Refund.refund_date >= start,
            Refund.refund_date <= end,
            *_live(),
        )
    )


async def by_card(session: AsyncSession) -> dict[int, int]:
    """Kart kimliğine göre toplam iade. Kartın bağlı limitini serbest bırakır."""
    rows = await session.execute(
        select(Expense.payment_method_id, func.coalesce(func.sum(Refund.amount_minor), 0))
        .join(Expense, Refund.expense_id == Expense.id)
        .where(
            Expense.payment_method_type_snapshot == TYPE_CREDIT_CARD,
            Expense.deleted_at.is_(None),
            *_live(),
        )
        .group_by(Expense.payment_method_id)
    )
    return dict(rows.all())


@dataclass(frozen=True, slots=True)
class StatementCredit:
    """Bir ekstreye düşen iade alacağı."""

    payment_method_id: int
    statement_date: date
    total_minor: int


async def statement_credits(
    session: AsyncSession, *, since: date
) -> list[StatementCredit]:
    """Ekstre bazında iade alacakları."""
    rows = await session.execute(
        select(
            Expense.payment_method_id,
            Refund.statement_date,
            func.coalesce(func.sum(Refund.amount_minor), 0),
        )
        .join(Expense, Refund.expense_id == Expense.id)
        .where(
            Expense.deleted_at.is_(None),
            Refund.statement_date.is_not(None),
            Refund.statement_date >= since,
            *_live(),
        )
        .group_by(Expense.payment_method_id, Refund.statement_date)
    )
    return [
        StatementCredit(
            payment_method_id=row[0], statement_date=row[1], total_minor=row[2]
        )
        for row in rows.all()
    ]


async def card_credit_due_in_month(
    session: AsyncSession, *, year: int, month: int
) -> int:
    """Son ödemesi bu aya düşen kart iadelerinin toplamı.

    Kart iadesi cebe ekstre gününde değil, o ekstrenin son ödeme gününde
    yansır: ödenecek tutarı azaltır.
    """
    start, end = month_bounds(year, month)
    return await session.scalar(
        select(func.coalesce(func.sum(Refund.amount_minor), 0))
        .join(Expense, Refund.expense_id == Expense.id)
        .where(
            Expense.deleted_at.is_(None),
            Refund.due_date.is_not(None),
            Refund.due_date >= start,
            Refund.due_date <= end,
            *_live(),
        )
    )
