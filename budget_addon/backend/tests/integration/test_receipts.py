"""Fiş fotoğrafları.

Fotoğrafın kendisi saklanmaz; Telegram dosya kimliği tutulur. Tutar hiçbir
zaman fotoğraftan okunmaz, fiş yalnızca kanıttır.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.bot import keyboards
from app.services.expenses import (
    ExpenseInput,
    attach_receipt,
    create_expense,
    latest_expense_for,
    soft_delete_expense,
)

pytestmark = pytest.mark.asyncio

FILE_ID = "AgACAgQAAxkBAAIB_2X"


async def _spend(session, user, fixtures, amount="500"):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 5),
            amount=amount,
            installment_count=1,
        ),
    )


async def test_a_receipt_is_stored_as_a_file_id(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures)

    await attach_receipt(
        async_session, user=people["aykut"], expense=expense, file_id=FILE_ID
    )

    assert expense.receipt_file_id == FILE_ID
    # Tutar ve plan degismez: fis yalnizca kanittir.
    assert expense.total_amount_minor == 50_000


async def test_the_latest_expense_is_the_one_a_caption_less_photo_attaches_to(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "100")
    newest = await _spend(async_session, people["aykut"], fixtures, "200")

    found = await latest_expense_for(
        async_session, user=people["aykut"], now=datetime.now(timezone.utc)
    )

    assert found.id == newest.id


async def test_another_persons_expense_is_never_picked(
    async_session, people, fixtures
):
    await _spend(async_session, people["aslihan"], fixtures)

    found = await latest_expense_for(
        async_session, user=people["aykut"], now=datetime.now(timezone.utc)
    )

    assert found is None


async def test_a_deleted_expense_is_never_picked(async_session, people, fixtures):
    expense = await _spend(async_session, people["aykut"], fixtures)
    await soft_delete_expense(async_session, user=people["aykut"], expense=expense)

    found = await latest_expense_for(
        async_session, user=people["aykut"], now=datetime.now(timezone.utc)
    )

    assert found is None


async def test_an_old_expense_is_outside_the_attach_window(
    async_session, people, fixtures
):
    """Günler önceki bir harcamaya yanlışlıkla fiş iliştirilmemelidir."""
    await _spend(async_session, people["aykut"], fixtures)

    much_later = datetime.now(timezone.utc) + timedelta(days=3)
    found = await latest_expense_for(
        async_session, user=people["aykut"], now=much_later
    )

    assert found is None


async def test_the_receipt_button_appears_only_when_there_is_a_receipt():
    without = keyboards.expense_actions(7)
    with_receipt = keyboards.expense_actions(7, has_receipt=True)

    assert len(without.inline_keyboard) == 1
    assert len(with_receipt.inline_keyboard) == 2
    assert with_receipt.inline_keyboard[1][0].callback_data == (
        f"{keyboards.CALLBACK_RECEIPT}:7"
    )
