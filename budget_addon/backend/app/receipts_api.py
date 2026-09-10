"""Fiş fotoğrafı ve hızlı giriş.

İkisi de önceden yalnızca Telegram botunda vardı ve bot kaldırılmadan önce
siteye taşındı. Hızlı girişin kuralları aynı kaldı: kategori tek başına
eşleşirse harcama bugünün tarihiyle nakit olarak hemen kaydedilir, eşleşmezse
kategori formda seçilir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .api import _expense_out, _reload
from .config import Settings, get_settings
from .database import get_session
from .models.category import Category
from .models.payment_method import TYPE_CASH, PaymentMethod
from .models.user import User
from .schemas import ExpenseOut
from .security.identity import current_user
from .services import receipts, tags
from .services.expenses import ExpenseError, ExpenseInput, create_expense, get_expense
from .services.quick_entry import NotAnExpense, parse_quick_entry
from .utils.time import local_today

router = APIRouter(prefix="/api")

UNPROCESSABLE = 422
TOO_LARGE_MESSAGE = "Fotoğraf 10 MB'tan büyük olamaz."
QUICK_ENTRY_HELP = (
    "Metin bir tutarla başlamalı. Örnek: 500 market veya 1250,50 yakıt benzin"
)


async def _expense_or_404(session: AsyncSession, expense_id: int):
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")
    return expense


# ---------------------------------------------------------------------------
# Fis fotografi
# ---------------------------------------------------------------------------


@router.put("/expenses/{expense_id}/receipt", status_code=status.HTTP_204_NO_CONTENT)
async def upload_receipt(
    expense_id: int,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    """Fotoğraf gövdenin kendisidir (ör. `Content-Type: image/jpeg`)."""
    expense = await _expense_or_404(session, expense_id)
    if int(request.headers.get("content-length") or 0) > receipts.MAX_RECEIPT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, TOO_LARGE_MESSAGE)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > receipts.MAX_RECEIPT_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, TOO_LARGE_MESSAGE)
    try:
        await receipts.save_receipt(
            session, settings, user=user, expense=expense, data=bytes(data)
        )
    except receipts.ReceiptError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc


@router.get("/expenses/{expense_id}/receipt")
async def read_receipt(
    expense_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    expense = await _expense_or_404(session, expense_id)
    path = receipts.receipt_file(settings, expense)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu harcamada fiş fotoğrafı yok")
    return FileResponse(
        path,
        media_type=receipts.MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        # Tarayici her seferinde sorar; fotograf degismediyse sunucu 304 doner.
        headers={"Cache-Control": "private, no-cache"},
    )


@router.delete("/expenses/{expense_id}/receipt", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    expense_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    expense = await _expense_or_404(session, expense_id)
    await receipts.remove_receipt(session, settings, user=user, expense=expense)


# ---------------------------------------------------------------------------
# Hizli giris
# ---------------------------------------------------------------------------


class QuickEntryIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class QuickEntryOut(BaseModel):
    expense: ExpenseOut | None = None
    """Doluysa harcama kaydedildi."""
    amount_minor: int | None = None
    description: str | None = None
    candidate_ids: list[int] = Field(default_factory=list)
    """Kategori belirsizse seçilebilecek kategoriler."""


@router.post("/expenses/quick", response_model=QuickEntryOut)
async def quick_entry(
    payload: QuickEntryIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> QuickEntryOut:
    categories = list(
        (
            await session.scalars(
                select(Category)
                .where(Category.is_active.is_(True))
                .order_by(Category.sort_order, Category.id)
            )
        ).all()
    )
    try:
        entry = parse_quick_entry(payload.text, categories)
    except NotAnExpense as exc:
        raise HTTPException(UNPROCESSABLE, QUICK_ENTRY_HELP) from exc

    if entry.needs_category_choice:
        return QuickEntryOut(
            amount_minor=entry.amount_minor,
            description=entry.description,
            candidate_ids=[category.id for category in entry.candidates],
        )

    cash = await session.scalar(
        select(PaymentMethod)
        .where(PaymentMethod.type == TYPE_CASH, PaymentMethod.is_active.is_(True))
        .order_by(PaymentMethod.id)
        .limit(1)
    )
    if cash is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nakit ödeme yöntemi bulunamadı. Ayarlardan bir nakit ödeme yöntemi ekleyin.",
        )

    try:
        expense = await create_expense(
            session,
            user=user,
            data=ExpenseInput(
                payment_method_id=cash.id,
                category_id=entry.category.id,
                transaction_date=local_today(settings.timezone),
                amount=entry.amount_minor,
                description=entry.description,
                # `#kisisel` yazan kisi harcamanin ortak gidere sayilmamasini ister.
                is_shared=not tags.marks_personal(entry.description),
            ),
        )
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return QuickEntryOut(expense=_expense_out(await _reload(session, expense.id)))
