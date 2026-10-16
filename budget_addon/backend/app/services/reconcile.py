"""Ekstre mutabakatı: bankanın ekstresi ile sistemin hesabını karşılaştırma.

Kişi bankanın kestiği ekstre tutarını yazar; sistem aynı ekstreye düşen
taksitlerin toplamını (iade alacakları düşülmüş olarak) yanına koyar. Fark
sıfırsa ekstre mutabıktır. Değilse satır satır kontrol edilir: bankada görülen
satır işaretlenir (`cleared`) ve işaretsiz kalan, eksik veya fazla olan kaydı
gösterir.

Mutabakat hiçbir tutarı değiştirmez. Eksik bir harcama varsa kişi onu
normal yoldan ekler; sistem farkı kendiliğinden "düzeltme" kaydıyla kapatmaz,
çünkü kapatılan fark, bulunması gereken bir hatayı gizlerdi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.installment import STATUS_CANCELLED, ExpenseInstallment
from ..models.payment_method import TYPE_CREDIT_CARD, PaymentMethod
from ..models.reconciliation import StatementReconciliation
from ..models.refund import Refund
from ..models.user import User

HISTORY_STATEMENTS = 12
UPCOMING_DAYS = 45
"""Henüz kesilmemiş ama yaklaşan ekstreler de listelenir; bankanın
uygulamasında "dönem içi işlemler" olarak görülebilirler."""


class ReconcileError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


async def _card(session: AsyncSession, payment_method_id: int) -> PaymentMethod:
    method = await session.get(PaymentMethod, payment_method_id)
    if method is None or method.type != TYPE_CREDIT_CARD:
        raise ReconcileError("Kredi kartı bulunamadı")
    return method


def _line_filters(payment_method_id: int) -> tuple:
    return (
        Expense.deleted_at.is_(None),
        Expense.payment_method_id == payment_method_id,
        Expense.payment_method_type_snapshot == TYPE_CREDIT_CARD,
        ExpenseInstallment.status != STATUS_CANCELLED,
    )


@dataclass(frozen=True, slots=True)
class StatementSummary:
    statement_date: date
    due_date: date
    ours_total_minor: int
    line_count: int
    cleared_count: int
    bank_total_minor: int | None
    saved_ours_total_minor: int | None

    @property
    def difference_minor(self) -> int | None:
        """Banka eksi sistem. Artıysa sistemde eksik kayıt var demektir."""
        if self.bank_total_minor is None:
            return None
        return self.bank_total_minor - self.ours_total_minor

    @property
    def is_reconciled(self) -> bool:
        return self.difference_minor == 0

    @property
    def changed_since(self) -> bool:
        """Mutabakattan sonra bu ekstreye düşen bir kayıt değişti mi."""
        return (
            self.saved_ours_total_minor is not None
            and self.saved_ours_total_minor != self.ours_total_minor
        )


async def _credits(
    session: AsyncSession, payment_method_id: int, dates: list[date] | None = None
) -> dict[date, int]:
    statement = (
        select(Refund.statement_date, func.coalesce(func.sum(Refund.amount_minor), 0))
        .join(Expense, Refund.expense_id == Expense.id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.payment_method_id == payment_method_id,
            Refund.deleted_at.is_(None),
            Refund.statement_date.is_not(None),
        )
        .group_by(Refund.statement_date)
    )
    if dates is not None:
        statement = statement.where(Refund.statement_date.in_(dates))
    rows = (await session.execute(statement)).tuples().all()
    return {when: int(total) for when, total in rows if when is not None}


async def statements(
    session: AsyncSession, *, payment_method_id: int, today: date
) -> list[StatementSummary]:
    """Kartın son ekstreleri ve yaklaşan ekstresi, en yenisi önce."""
    await _card(session, payment_method_id)
    rows = (
        await session.execute(
            select(
                ExpenseInstallment.statement_date,
                func.max(ExpenseInstallment.due_date),
                func.sum(ExpenseInstallment.amount_minor),
                func.count(ExpenseInstallment.id),
                func.sum(case((ExpenseInstallment.cleared.is_(True), 1), else_=0)),
            )
            .join(Expense, ExpenseInstallment.expense_id == Expense.id)
            .where(
                *_line_filters(payment_method_id),
                ExpenseInstallment.statement_date <= today + timedelta(days=UPCOMING_DAYS),
            )
            .group_by(ExpenseInstallment.statement_date)
            .order_by(ExpenseInstallment.statement_date.desc())
            .limit(HISTORY_STATEMENTS + 2)
        )
    ).all()
    if not rows:
        return []
    dates = [row[0] for row in rows]
    credits = await _credits(session, payment_method_id, dates)
    saved = {
        item.statement_date: item
        for item in (
            await session.scalars(
                select(StatementReconciliation).where(
                    StatementReconciliation.payment_method_id == payment_method_id,
                    StatementReconciliation.statement_date.in_(dates),
                )
            )
        ).all()
    }
    return [
        StatementSummary(
            statement_date=statement_date,
            due_date=due_date,
            ours_total_minor=int(total) - credits.get(statement_date, 0),
            line_count=int(count),
            cleared_count=int(cleared or 0),
            bank_total_minor=saved[statement_date].bank_total_minor if statement_date in saved else None,
            saved_ours_total_minor=(
                saved[statement_date].ours_total_minor if statement_date in saved else None
            ),
        )
        for statement_date, due_date, total, count, cleared in rows
    ]


@dataclass(frozen=True, slots=True)
class StatementLine:
    kind: str
    """`installment` veya `refund`."""
    id: int
    expense_id: int
    public_id: str
    description: str | None
    transaction_date: date
    amount_minor: int
    """İade alacağı eksi yazılır."""
    installment_number: int | None
    installment_count: int | None
    cleared: bool


@dataclass(slots=True)
class StatementDetail:
    summary: StatementSummary
    lines: list[StatementLine] = field(default_factory=list)
    note: str | None = None

    @property
    def cleared_total_minor(self) -> int:
        return sum(line.amount_minor for line in self.lines if line.cleared)


async def detail(
    session: AsyncSession, *, payment_method_id: int, statement_date: date
) -> StatementDetail:
    """Bir ekstrenin satırları ve mutabakat durumu."""
    await _card(session, payment_method_id)
    installments = (
        await session.execute(
            select(ExpenseInstallment, Expense)
            .join(Expense, ExpenseInstallment.expense_id == Expense.id)
            .where(
                *_line_filters(payment_method_id),
                ExpenseInstallment.statement_date == statement_date,
            )
            .order_by(Expense.transaction_date, Expense.id)
        )
    ).all()
    refunds = (
        await session.execute(
            select(Refund, Expense)
            .join(Expense, Refund.expense_id == Expense.id)
            .where(
                Expense.deleted_at.is_(None),
                Expense.payment_method_id == payment_method_id,
                Refund.deleted_at.is_(None),
                Refund.statement_date == statement_date,
            )
            .order_by(Refund.refund_date, Refund.id)
        )
    ).all()
    lines = [
        StatementLine(
            kind="installment",
            id=line.id,
            expense_id=expense.id,
            public_id=expense.public_id,
            description=expense.description,
            transaction_date=expense.transaction_date,
            amount_minor=line.amount_minor,
            installment_number=line.installment_number,
            installment_count=line.installment_count,
            cleared=line.cleared,
        )
        for line, expense in installments
    ] + [
        StatementLine(
            kind="refund",
            id=refund.id,
            expense_id=expense.id,
            public_id=expense.public_id,
            description=f"İade: {expense.description or expense.public_id}",
            transaction_date=refund.refund_date,
            amount_minor=-refund.amount_minor,
            installment_number=None,
            installment_count=None,
            # Iade satirlari bankada ayrica isaretlenmez; tutar zaten dusulur.
            cleared=True,
        )
        for refund, expense in refunds
    ]

    saved = await session.scalar(
        select(StatementReconciliation).where(
            StatementReconciliation.payment_method_id == payment_method_id,
            StatementReconciliation.statement_date == statement_date,
        )
    )
    total = sum(line.amount_minor for line in lines)
    due = max((line.due_date for line, _ in installments), default=statement_date)
    summary = StatementSummary(
        statement_date=statement_date,
        due_date=due,
        ours_total_minor=total,
        line_count=len(installments),
        cleared_count=sum(1 for line, _ in installments if line.cleared),
        bank_total_minor=saved.bank_total_minor if saved else None,
        saved_ours_total_minor=saved.ours_total_minor if saved else None,
    )
    return StatementDetail(summary=summary, lines=lines, note=saved.note if saved else None)


async def set_cleared(
    session: AsyncSession, *, payment_method_id: int, installment_ids: list[int], cleared: bool
) -> int:
    """Taksit satırlarını "bankada görüldü" olarak işaretler veya işareti kaldırır.

    Yalnızca bu kartın satırları değişir; başka karta ait bir kimlik sessizce
    atlanır.
    """
    await _card(session, payment_method_id)
    if not installment_ids:
        return 0
    own = select(ExpenseInstallment.id).join(
        Expense, ExpenseInstallment.expense_id == Expense.id
    ).where(
        Expense.payment_method_id == payment_method_id,
        ExpenseInstallment.id.in_(installment_ids),
    )
    result = await session.execute(
        update(ExpenseInstallment)
        .where(ExpenseInstallment.id.in_(own.scalar_subquery()))
        .values(cleared=cleared)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return result.rowcount or 0


async def save(
    session: AsyncSession,
    *,
    user: User,
    payment_method_id: int,
    statement_date: date,
    bank_total_minor: int,
    note: str | None,
) -> StatementDetail:
    """Bankanın ekstre tutarını kaydeder; sistemin o anki hesabını yanına yazar."""
    current = await detail(
        session, payment_method_id=payment_method_id, statement_date=statement_date
    )
    saved = await session.scalar(
        select(StatementReconciliation).where(
            StatementReconciliation.payment_method_id == payment_method_id,
            StatementReconciliation.statement_date == statement_date,
        )
    )
    if saved is None:
        saved = StatementReconciliation(
            payment_method_id=payment_method_id, statement_date=statement_date
        )
        session.add(saved)
    saved.bank_total_minor = bank_total_minor
    saved.ours_total_minor = current.summary.ours_total_minor
    saved.note = (note or "").strip() or None
    saved.reconciled_by_user_id = user.id
    await session.commit()
    return await detail(
        session, payment_method_id=payment_method_id, statement_date=statement_date
    )


async def forget(
    session: AsyncSession, *, payment_method_id: int, statement_date: date
) -> None:
    saved = await session.scalar(
        select(StatementReconciliation).where(
            StatementReconciliation.payment_method_id == payment_method_id,
            StatementReconciliation.statement_date == statement_date,
        )
    )
    if saved is not None:
        await session.delete(saved)
        await session.commit()
