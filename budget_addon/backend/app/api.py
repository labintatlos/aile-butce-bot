"""HTTP arayüzü.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını çağırır,
sonucu biçimlendirir. Telegram bot handler'ları da aynı servisleri çağıracağı
için iki arayüz arasında hesaplama farkı oluşamaz.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.category import Category
from .models.payment_method import DEFAULT_CURRENCY, PaymentMethod
from .models.user import User
from .schemas import (
    BootstrapOut,
    CategoryOut,
    ExpenseCreateIn,
    ExpenseOut,
    ExpenseUpdateIn,
    InstallmentOut,
    InstallmentPlanOut,
    MonthlySpendingOut,
    Money,
    NamedTotalOut,
    ObligationOut,
    ObligationsOut,
    PaymentMethodOut,
    SchedulePreviewIn,
    SchedulePreviewOut,
    StatementOut,
    UserOut,
)
from .security.identity import current_user
from .services import reports
from .services.expenses import (
    ExpenseError,
    ExpenseInput,
    create_expense,
    get_expense,
    soft_delete_expense,
    update_expense,
)
from .services.finance.installments import build_schedule
from .services.finance.money import parse_amount_to_minor
from .utils.time import local_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

BASIS_LABELS = {
    reports.BASIS_STATEMENT: "Ekstre Bazlı",
    reports.BASIS_DUE: "Son Ödeme Bazlı",
}


def _expense_out(expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        public_id=expense.public_id,
        created_by=expense.created_by.display_name if expense.created_by else "",
        category=CategoryOut.model_validate(expense.category),
        payment_method_name=expense.payment_method_name_snapshot,
        transaction_date=expense.transaction_date,
        total=Money.of(expense.total_amount_minor),
        installment_count=expense.installment_count,
        description=expense.description,
        installments=[
            InstallmentOut(
                number=line.installment_number,
                count=line.installment_count,
                amount=Money.of(line.amount_minor),
                statement_date=line.statement_date,
                due_date=line.due_date,
                status=line.status,
            )
            for line in expense.installments
        ],
    )


def _named_total(item: reports.NamedTotal) -> NamedTotalOut:
    return NamedTotalOut(
        id=item.id,
        name=item.name,
        emoji=item.emoji,
        total=Money.of(item.total_minor),
        transaction_count=item.transaction_count,
    )


# ---------------------------------------------------------------------------
# Acilis
# ---------------------------------------------------------------------------


@router.get("/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BootstrapOut:
    """Arayüzün açılışta ihtiyaç duyduğu her şey tek istekte."""
    categories = (
        await session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
    ).all()
    methods = (
        await session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.is_active.is_(True))
            .order_by(PaymentMethod.type, PaymentMethod.name)
        )
    ).all()
    return BootstrapOut(
        user=UserOut.model_validate(user),
        categories=[CategoryOut.model_validate(c) for c in categories],
        payment_methods=[PaymentMethodOut.model_validate(m) for m in methods],
        today=local_today(settings.timezone),
        currency=DEFAULT_CURRENCY,
    )


# ---------------------------------------------------------------------------
# Harcamalar
# ---------------------------------------------------------------------------


@router.post("/expenses/preview", response_model=SchedulePreviewOut)
async def preview_schedule(
    payload: SchedulePreviewIn,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SchedulePreviewOut:
    """Kaydetmeden önce taksit ve ekstre özetini hesaplar (§17).

    Hiçbir şey yazmaz; yalnızca kaydedilecek olanı gösterir.
    """
    method = await session.get(PaymentMethod, payload.payment_method_id)
    if method is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme yöntemi bulunamadı")
    try:
        total_minor = parse_amount_to_minor(payload.amount)
        schedule = build_schedule(
            total_minor=total_minor,
            installment_count=payload.installment_count,
            transaction_date=payload.transaction_date,
            statement_day=method.statement_day,
            due_day=method.due_day,
            cutoff_inclusive=method.cutoff_inclusive,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return SchedulePreviewOut(
        total=Money.of(total_minor),
        installment_count=len(schedule),
        installment_amount=Money.of(schedule[0].amount_minor),
        first_statement_date=schedule[0].statement_date if method.is_credit_card else None,
        first_due_date=schedule[0].due_date if method.is_credit_card else None,
        last_due_date=schedule[-1].due_date if method.is_credit_card else None,
        is_credit_card=method.is_credit_card,
    )


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ExpenseCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    try:
        expense = await create_expense(
            session,
            user=user,
            data=ExpenseInput(
                payment_method_id=payload.payment_method_id,
                category_id=payload.category_id,
                transaction_date=payload.transaction_date,
                amount=payload.amount,
                installment_count=payload.installment_count,
                description=payload.description,
            ),
        )
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _expense_out(await _reload(session, expense.id))


async def _reload(session: AsyncSession, expense_id: int):
    from sqlalchemy.orm import selectinload

    from .models.expense import Expense

    return await session.scalar(
        select(Expense)
        .where(Expense.id == expense_id)
        .options(
            selectinload(Expense.installments),
            selectinload(Expense.category),
            selectinload(Expense.created_by),
        )
    )


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
async def read(
    expense_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")
    return _expense_out(await _reload(session, expense_id))


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def edit(
    expense_id: int,
    payload: ExpenseUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _expense_out(await _reload(session, expense_id))
    try:
        await update_expense(session, user=user, expense=expense, changes=changes)
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _expense_out(await _reload(session, expense_id))


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    expense_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")
    await soft_delete_expense(session, user=user, expense=expense)


# ---------------------------------------------------------------------------
# Raporlar
# ---------------------------------------------------------------------------


@router.get("/reports/spending/monthly", response_model=MonthlySpendingOut)
async def monthly_spending_report(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MonthlySpendingOut:
    """Aylık **harcama** raporu. Tutarlar harcama toplamıdır, taksit değil."""
    today = local_today(settings.timezone)
    report = await reports.monthly_spending(
        session, year=year or today.year, month=month or today.month
    )
    largest = None
    if report.largest_expense is not None:
        largest = _expense_out(await _reload(session, report.largest_expense.id))
    return MonthlySpendingOut(
        year=report.year,
        month=report.month,
        total=Money.of(report.total_minor),
        transaction_count=report.transaction_count,
        cash_total=Money.of(report.cash_total_minor),
        card_total=Money.of(report.card_total_minor),
        by_user=[_named_total(item) for item in report.by_user],
        by_category=[_named_total(item) for item in report.by_category],
        largest_expense=largest,
    )


@router.get("/reports/cashflow/statements", response_model=list[StatementOut])
async def statements_report(
    since: date | None = None,
    until: date | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[StatementOut]:
    """Kart bazlı yaklaşan ekstreler. **Nakit akışı** bakışıdır."""
    rows = await reports.upcoming_statements(
        session, since=since or local_today(settings.timezone), until=until
    )
    return [
        StatementOut(
            payment_method_id=row.payment_method_id,
            payment_method_name=row.payment_method_name,
            statement_date=row.statement_date,
            due_date=row.due_date,
            total=Money.of(row.total_minor),
            installment_count=row.installment_count,
        )
        for row in rows
    ]


@router.get("/reports/cashflow/upcoming", response_model=ObligationsOut)
async def upcoming_obligations(
    months: int = Query(default=reports.DEFAULT_FORECAST_MONTHS, ge=1, le=36),
    basis: str = Query(default=reports.BASIS_STATEMENT),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ObligationsOut:
    """Gelecek kredi kartı yükü. Hangi bakış kullanıldığı yanıtta yazar."""
    if basis not in BASIS_LABELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Geçersiz bakış açısı")
    rows = await reports.future_obligations(
        session, start=local_today(settings.timezone), months=months, basis=basis
    )
    return ObligationsOut(
        basis=basis,
        basis_label=BASIS_LABELS[basis],
        months=[
            ObligationOut(
                year=row.year,
                month=row.month,
                total=Money.of(row.total_minor),
                installment_count=row.installment_count,
            )
            for row in rows
        ],
    )


@router.get("/reports/installments", response_model=list[InstallmentPlanOut])
async def installment_plans(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[InstallmentPlanOut]:
    """Aktif taksitli alışverişler ve kalan borç."""
    plans = await reports.active_installment_plans(session)
    return [
        InstallmentPlanOut(
            expense_id=plan.expense_id,
            public_id=plan.public_id,
            description=plan.description,
            category_name=plan.category_name,
            payment_method_name=plan.payment_method_name,
            total=Money.of(plan.total_minor),
            remaining=Money.of(plan.remaining_minor),
            monthly=Money.of(plan.monthly_minor),
            position=plan.paid_position,
        )
        for plan in plans
    ]
