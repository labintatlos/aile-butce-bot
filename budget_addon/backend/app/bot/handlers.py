"""Telegram handler'ları.

Handler'lar iş kuralı içermez: kullanıcı girdisini okur, `services` katmanını
çağırır, sonucu biçimlendirir. Hesaplamanın tamamı API ile paylaşılan aynı
servislerden gelir.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models.category import Category
from ..models.payment_method import TYPE_CASH, PaymentMethod
from ..models.user import User
from ..services import reports, search as search_service, settings_service
from ..services.expenses import (
    ExpenseError,
    ExpenseInput,
    create_expense,
    get_expense,
    soft_delete_expense,
    update_expense,
)
from ..services.quick_entry import NotAnExpense, parse_quick_entry
from ..utils.time import local_today
from . import keyboards, messages
from .formatting import expense_receipt

logger = logging.getLogger(__name__)

_pending_edits: dict[int, int] = {}
"""Telegram kullanicisi -> duzenlemek uzere sectigi harcama.

Bellek ici tutulur; bot yeniden baslarsa yarim kalan duzenleme unutulur ve
kullanici islemi bastan yapar. Kalici bir durum saklamaya deger degil."""

router = Router()

GENERIC_ERROR = (
    "⚠️ İşlem kaydedilemedi. Verileriniz kaydedilmedi. Lütfen tekrar deneyin."
)
WELCOME = (
    "Merhaba {name}! 👋\n\n"
    "Aile bütçesi botuna hoş geldin. Aşağıdaki menüden ilerleyebilir ya da"
    " doğrudan <code>500 market</code> gibi yazarak hızlı kayıt yapabilirsin."
)
FORM_UNAVAILABLE = (
    "Harcama formu henüz yapılandırılmamış.\n\n" + messages.quick_entry_help()
)


async def _active_categories(session: AsyncSession) -> list[Category]:
    return list(
        (
            await session.scalars(
                select(Category)
                .where(Category.is_active.is_(True))
                .order_by(Category.sort_order, Category.name)
            )
        ).all()
    )


async def _cash_method(session: AsyncSession) -> PaymentMethod | None:
    return await session.scalar(
        select(PaymentMethod).where(
            PaymentMethod.type == TYPE_CASH, PaymentMethod.is_active.is_(True)
        )
    )


@router.message(CommandStart())
async def start(message: Message, user: User, settings: Settings) -> None:
    await message.answer(
        WELCOME.format(name=user.display_name),
        reply_markup=keyboards.main_menu(settings.public_url or None),
        parse_mode="HTML",
    )


@router.message(Command("yardim"))
async def help_command(message: Message) -> None:
    await message.answer(messages.quick_entry_help(), parse_mode="HTML")


@router.message(F.text == keyboards.BUTTON_ADD)
async def add_expense_prompt(message: Message, settings: Settings) -> None:
    """Mini App adresi yoksa kullanıcı yine de kayıt yapabilmelidir."""
    if not settings.public_url:
        await message.answer(FORM_UNAVAILABLE, parse_mode="HTML")
        return
    await message.answer("Formu açmak için ➕ Harcama Ekle düğmesini kullan.")


@router.message(F.text == keyboards.BUTTON_MONTH)
async def monthly(message: Message, session: AsyncSession, settings: Settings) -> None:
    today = local_today(settings.timezone)
    report = await reports.monthly_spending(session, year=today.year, month=today.month)
    await message.answer(messages.monthly_report(report))


@router.message(F.text == keyboards.BUTTON_STATEMENTS)
async def statements(message: Message, session: AsyncSession, settings: Settings) -> None:
    rows = await reports.upcoming_statements(
        session, since=local_today(settings.timezone)
    )
    await message.answer(messages.statements_report(rows))


@router.message(F.text == keyboards.BUTTON_INSTALLMENTS)
async def installments(message: Message, session: AsyncSession) -> None:
    plans = await reports.active_installment_plans(session)
    await message.answer(messages.installment_plans_report(plans))


@router.message(F.text == keyboards.BUTTON_UPCOMING)
async def upcoming(message: Message, session: AsyncSession, settings: Settings) -> None:
    months = await reports.future_obligations(
        session, start=local_today(settings.timezone), basis=reports.BASIS_STATEMENT
    )
    await message.answer(
        messages.obligations_report(
            months, basis_label=keyboards.BASIS_STATEMENT_LABEL
        )
    )


SEARCH_PREFIX = "ara "


@router.message(F.text == keyboards.BUTTON_ANALYSIS)
async def analysis(message: Message, session: AsyncSession, settings: Settings) -> None:
    """Kategori dağılımı ve önceki aya göre değişim."""
    today = local_today(settings.timezone)
    current = await reports.monthly_spending(
        session, year=today.year, month=today.month
    )
    previous_month = today.month - 1 or 12
    previous_year = today.year if today.month > 1 else today.year - 1
    previous = await reports.monthly_spending(
        session, year=previous_year, month=previous_month
    )
    await message.answer(messages.analysis_report(current, previous), parse_mode="HTML")


@router.message(F.text == keyboards.BUTTON_SEARCH)
async def search_prompt(message: Message) -> None:
    await message.answer(messages.search_help(), parse_mode="HTML")


@router.message(F.text == keyboards.BUTTON_SETTINGS)
async def settings_overview(message: Message, session: AsyncSession) -> None:
    methods = await settings_service.list_payment_methods(session)
    categories = await settings_service.list_categories(session)
    await message.answer(
        messages.settings_overview(methods, categories), parse_mode="HTML"
    )


@router.message(F.text.lower().startswith(SEARCH_PREFIX))
async def search_expenses_handler(message: Message, session: AsyncSession) -> None:
    term = (message.text or "")[len(SEARCH_PREFIX):].strip()
    if not term:
        await message.answer(messages.search_help(), parse_mode="HTML")
        return
    page = await search_service.search_expenses(
        session, search_service.SearchFilters(text=term), page_size=10
    )
    await message.answer(messages.search_results(page, term=term), parse_mode="HTML")


@router.message(F.text & ~F.text.startswith("/"))
async def quick_entry(
    message: Message, user: User, session: AsyncSession, settings: Settings
) -> None:
    """Serbest metinden hızlı harcama kaydı (§6b).

    Metin tutarla başlamıyorsa harcama sayılmaz ve kullanıcıya ne
    yapabileceği anlatılır.
    """
    categories = await _active_categories(session)
    try:
        entry = parse_quick_entry(message.text or "", categories)
    except NotAnExpense:
        await message.answer(messages.quick_entry_help(), parse_mode="HTML")
        return

    if entry.needs_category_choice:
        await message.answer(
            messages.quick_entry_needs_category(entry.amount_minor),
            reply_markup=keyboards.category_choices(entry.candidates),
        )
        return

    cash = await _cash_method(session)
    if cash is None:
        await message.answer(GENERIC_ERROR)
        logger.error("Nakit ödeme yöntemi bulunamadı; seed çalışmamış olabilir")
        return

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
            ),
        )
    except (ExpenseError, ValueError) as exc:
        await message.answer(f"⚠️ {exc}")
        return
    except Exception:
        logger.exception("Hızlı giriş sırasında beklenmeyen hata")
        await message.answer(GENERIC_ERROR)
        return

    await message.answer(
        expense_receipt(
            public_id=expense.public_id,
            category_name=entry.category.name,
            category_emoji=entry.category.emoji,
            description=expense.description,
            total_minor=expense.total_amount_minor,
            payment_method_name=expense.payment_method_name_snapshot,
            installment_count=expense.installment_count,
            first_statement_date=None,
            is_credit_card=False,
        ),
        reply_markup=keyboards.expense_actions(expense.id),
    )


@router.callback_query(F.data.startswith(keyboards.CALLBACK_DELETE_CONFIRM))
async def delete_confirmed(
    query: CallbackQuery, user: User, session: AsyncSession
) -> None:
    expense_id = keyboards.parse_callback(
        query.data, keyboards.CALLBACK_DELETE_CONFIRM
    )
    expense = await get_expense(session, expense_id) if expense_id else None
    if expense is None:
        await query.answer("Harcama bulunamadı", show_alert=True)
        return
    await soft_delete_expense(session, user=user, expense=expense)
    await query.message.edit_text(f"🗑 #{expense.public_id} silindi.")
    await query.answer()


@router.callback_query(F.data.startswith(keyboards.CALLBACK_DELETE_CANCEL))
async def delete_cancelled(query: CallbackQuery) -> None:
    await query.message.edit_text("Silme iptal edildi.")
    await query.answer()


@router.callback_query(F.data.startswith(keyboards.CALLBACK_DELETE))
async def delete_requested(query: CallbackQuery, session: AsyncSession) -> None:
    """Silmeden önce onay sorulur (§27)."""
    expense_id = keyboards.parse_callback(query.data, keyboards.CALLBACK_DELETE)
    expense = await get_expense(session, expense_id) if expense_id else None
    if expense is None:
        await query.answer("Harcama bulunamadı", show_alert=True)
        return
    await query.message.answer(
        messages.deletion_prompt(expense.public_id, expense.total_amount_minor),
        reply_markup=keyboards.delete_confirmation(expense.id),
    )
    await query.answer()


@router.callback_query(F.data.startswith(keyboards.CALLBACK_CATEGORY))
async def change_category(
    query: CallbackQuery, user: User, session: AsyncSession
) -> None:
    """Seçilen kategoriyi uygular.

    Kategori değişikliği taksit planına dokunmaz (docs/FINANCE_RULES.md, E2),
    bu yüzden bot üzerinden güvenle yapılabilir.
    """
    category_id = keyboards.parse_callback(query.data, keyboards.CALLBACK_CATEGORY)
    expense_id = _pending_edits.pop(query.from_user.id, None)
    if category_id is None or expense_id is None:
        await query.answer("Bu seçim artık geçerli değil.", show_alert=True)
        return

    expense = await get_expense(session, expense_id)
    category = await session.get(Category, category_id)
    if expense is None or category is None:
        await query.answer("Harcama bulunamadı.", show_alert=True)
        return

    await update_expense(
        session, user=user, expense=expense, changes={"category_id": category.id}
    )
    await query.message.edit_text(
        f"✅ #{expense.public_id} kategorisi {category.emoji} {category.name}"
        " olarak güncellendi."
    )
    await query.answer()


@router.callback_query(F.data.startswith(keyboards.CALLBACK_EDIT))
async def edit_requested(query: CallbackQuery, session: AsyncSession) -> None:
    """Harcamayı gösterir ve kategori değiştirme seçeneği sunar."""
    expense_id = keyboards.parse_callback(query.data, keyboards.CALLBACK_EDIT)
    expense = await get_expense(session, expense_id) if expense_id else None
    if expense is None:
        await query.answer("Harcama bulunamadı.", show_alert=True)
        return

    _pending_edits[query.from_user.id] = expense.id
    categories = await _active_categories(session)
    await query.message.answer(
        messages.expense_detail(expense),
        reply_markup=keyboards.category_choices(categories),
        parse_mode="HTML",
    )
    await query.answer()
