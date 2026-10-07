"""Harcama, arama ve iade uç noktaları.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını
çağırır, sonucu biçimlendirir.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.payment_method import PaymentMethod
from .models.user import User
from .schemas import (
    CategoryOut,
    ExpenseCreateIn,
    ExpenseOut,
    ExpenseUpdateIn,
    InstallmentOut,
    Money,
    RefundCreateIn,
    RefundOut,
    SchedulePreviewIn,
    SchedulePreviewOut,
    SearchResultOut,
)
from .security.identity import current_user
from .services import (
    refunds,
)
from .services import (
    search as search_service,
)
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

router = APIRouter()


def expense_out(expense) -> ExpenseOut:
    today = local_today()
    return ExpenseOut(
        id=expense.id,
        public_id=expense.public_id,
        created_by=expense.created_by.display_name if expense.created_by else "",
        category=CategoryOut.model_validate(expense.category),
        payment_method_id=expense.payment_method_id,
        payment_method_name=expense.payment_method_name_snapshot,
        transaction_date=expense.transaction_date,
        total=Money.of(expense.total_amount_minor),
        installment_count=expense.installment_count,
        description=expense.description,
        is_shared=expense.is_shared,
        owner_user_id=expense.owner_user_id,
        owner_name=expense.owner.display_name if expense.owner else None,
        has_receipt=bool(expense.receipt_path),
        installments=[
            InstallmentOut(
                number=line.installment_number,
                count=line.installment_count,
                amount=Money.of(line.amount_minor),
                statement_date=line.statement_date,
                due_date=line.due_date,
                status=_installment_status(line, today),
            )
            for line in expense.installments
        ],
    )


def _installment_status(line, today) -> str:
    """Son ödeme tarihi geçmiş taksit ödenmiş sayılır."""
    if line.status == "scheduled" and line.due_date < today:
        return "paid"
    return line.status


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
            due_offset_days=method.due_offset_days,
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
                is_shared=payload.is_shared,
                owner_user_id=payload.owner_user_id,
            ),
        )
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return expense_out(await reload_expense(session, expense.id))


async def reload_expense(session: AsyncSession, expense_id: int):
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
    return expense_out(await reload_expense(session, expense_id))


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
        return expense_out(await reload_expense(session, expense_id))
    try:
        await update_expense(session, user=user, expense=expense, changes=changes)
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return expense_out(await reload_expense(session, expense_id))


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


@router.get("/expenses", response_model=SearchResultOut)
async def search(
    text: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    payment_method_id: int | None = None,
    created_by_user_id: int | None = None,
    min_amount_minor: int | None = Query(default=None, ge=0),
    max_amount_minor: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=search_service.DEFAULT_PAGE_SIZE, ge=1, le=search_service.MAX_PAGE_SIZE),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SearchResultOut:
    """Harcama arama ve filtreleme (§25)."""
    result = await search_service.search_expenses(
        session,
        search_service.SearchFilters(
            text=text,
            date_from=date_from,
            date_to=date_to,
            category_id=category_id,
            payment_method_id=payment_method_id,
            created_by_user_id=created_by_user_id,
            min_amount_minor=min_amount_minor,
            max_amount_minor=max_amount_minor,
        ),
        page=page,
        page_size=page_size,
    )
    return SearchResultOut(
        items=[expense_out(expense) for expense in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
        has_next=result.has_next,
    )


def _refund_out(refund) -> RefundOut:
    return RefundOut(
        id=refund.id,
        expense_id=refund.expense_id,
        amount=Money.of(refund.amount_minor),
        refund_date=refund.refund_date,
        statement_date=refund.statement_date,
        due_date=refund.due_date,
        notes=refund.notes,
    )


@router.get("/expenses/{expense_id}/refunds", response_model=list[RefundOut])
async def read_refunds(
    expense_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RefundOut]:
    return [
        _refund_out(refund)
        for refund in await refunds.list_for_expense(session, expense_id)
    ]


@router.post(
    "/expenses/{expense_id}/refunds",
    response_model=RefundOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_refund(
    expense_id: int,
    payload: RefundCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RefundOut:
    try:
        refund = await refunds.create_refund(
            session,
            user=user,
            expense_id=expense_id,
            amount=payload.amount_minor,
            refund_date=payload.refund_date or local_today(settings.timezone),
            notes=payload.notes,
        )
    except refunds.RefundError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _refund_out(refund)


@router.delete("/refunds/{refund_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_refund(
    refund_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    refund = await refunds.get_refund(session, refund_id)
    if refund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "İade kaydı bulunamadı")
    await refunds.soft_delete_refund(session, user=user, refund=refund)
