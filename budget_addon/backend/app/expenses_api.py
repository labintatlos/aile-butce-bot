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
    BulkIdsIn,
    BulkResultOut,
    BulkRevertIn,
    BulkUpdateIn,
    CategoryOut,
    ExpenseCreateIn,
    ExpenseOut,
    ExpenseUpdateIn,
    InstallmentOut,
    Money,
    PreviousValuesOut,
    RefundCreateIn,
    RefundOut,
    SchedulePreviewIn,
    SchedulePreviewOut,
    SearchResultOut,
    SplitOut,
)
from .security.identity import current_user
from .services import (
    bulk,
    refunds,
)
from .services import (
    search as search_service,
)
from .services.expenses import (
    ExpenseError,
    ExpenseInput,
    SplitInput,
    create_expense,
    get_expense,
    restore_expense,
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
        splits=[
            SplitOut(
                category_id=part.category_id,
                category_name=part.category.name if part.category else "",
                category_emoji=part.category.emoji if part.category else "",
                amount=Money.of(part.amount_minor),
                note=part.note,
            )
            for part in expense.splits
        ],
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
                splits=tuple(
                    SplitInput(category_id=part.category_id, amount=part.amount, note=part.note)
                    for part in payload.splits
                ),
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
            selectinload(Expense.splits),
        )
        .execution_options(populate_existing=True)
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
    if payload.splits is not None:
        changes["splits"] = [
            SplitInput(category_id=part.category_id, amount=part.amount, note=part.note)
            for part in payload.splits
        ]
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


def bulk_out(result: bulk.BulkResult) -> BulkResultOut:
    return BulkResultOut(
        changed=result.changed,
        skipped=result.skipped,
        previous=[
            PreviousValuesOut(
                expense_id=item.expense_id,
                category_id=item.category_id,
                description=item.description,
                is_shared=item.is_shared,
                owner_user_id=item.owner_user_id,
            )
            for item in result.previous
        ],
    )


@router.post("/expenses/bulk/update", response_model=BulkResultOut)
async def bulk_update(
    payload: BulkUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> BulkResultOut:
    """Seçilen harcamalara aynı değişikliği uygular; önceki değerleri döndürür."""
    changes = payload.model_dump(exclude={"ids"}, exclude_none=True)
    if payload.is_shared is False and payload.owner_user_id is None:
        changes["owner_user_id"] = None
    try:
        result = await bulk.bulk_update(session, user=user, ids=payload.ids, changes=changes)
    except (bulk.BulkError, ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return bulk_out(result)


@router.post("/expenses/bulk/revert", response_model=BulkResultOut)
async def bulk_revert(
    payload: BulkRevertIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> BulkResultOut:
    """Toplu işlemden önceki değerleri geri yazar ("Geri al")."""
    try:
        result = await bulk.revert(
            session, user=user, items=[item.model_dump() for item in payload.items]
        )
    except (bulk.BulkError, ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return bulk_out(result)


@router.post("/expenses/bulk/delete", response_model=BulkResultOut)
async def bulk_delete(
    payload: BulkIdsIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> BulkResultOut:
    try:
        result = await bulk.bulk_delete(session, user=user, ids=payload.ids)
    except bulk.BulkError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return bulk_out(result)


@router.post("/expenses/bulk/restore", response_model=BulkResultOut)
async def bulk_restore(
    payload: BulkIdsIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> BulkResultOut:
    try:
        result = await bulk.bulk_restore(session, user=user, ids=payload.ids)
    except bulk.BulkError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return bulk_out(result)


# Toplu yollardan SONRA tanimlanir: once tanimlansaydi `/expenses/bulk/restore`
# istegi buraya duser ve "bulk" kimlik olarak okunamadigi icin 422 donerdi.
@router.post("/expenses/{expense_id}/restore", response_model=ExpenseOut)
async def restore(
    expense_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    """Silinmiş harcamayı geri getirir ("Geri al")."""
    expense = await get_expense(session, expense_id, include_deleted=True)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")
    await restore_expense(session, user=user, expense=expense)
    return expense_out(await reload_expense(session, expense_id))


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
