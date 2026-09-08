"""Kart ve kategori yönetimi komutları.

Komut dilbilgisi bilinçli olarak basit ve deterministiktir; doğal dil
yorumlama yapılmaz. Adlar boşluk içerebildiği için, ad ile sayıların
karıştığı komutlarda `|` ayracı kullanılır.

    /kartekle Aykut Kredi Kartı 2 | 26 10
    /kartad 3 Yeni Kart Adı
    /kartgun 3 26 10
    /kartsil 3
    /kartpasif 3      /kartaktif 3

    /kategoriekle 🎬 Sinema
    /kategoriad 5 Yeni Ad
    /kategorisil 5
    /kategoripasif 5  /kategoriaktif 5

Handler'lar iş kuralı içermez; doğrulama ve yazma `settings_service` içinde
yapılır.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.category import Category
from ..models.payment_method import TYPE_CREDIT_CARD, PaymentMethod
from ..models.user import User
from ..services import settings_service
from . import messages

logger = logging.getLogger(__name__)

router = Router()

NAME_SEPARATOR = "|"
CARD_DAY_COUNT = 2
HISTORY_UNCHANGED_NOTE = (
    "Geçmiş harcamaların taksit planı değişmedi; yeni ayar bundan sonraki"
    " harcamalara uygulanır."
)


def _arguments(message: Message) -> str:
    """Komut adından sonraki ham metni verir."""
    text = message.text or ""
    _, _, rest = text.partition(" ")
    return rest.strip()


async def _find_card(session: AsyncSession, raw_id: str) -> PaymentMethod | None:
    try:
        return await session.get(PaymentMethod, int(raw_id))
    except ValueError:
        return None


async def _find_category(session: AsyncSession, raw_id: str) -> Category | None:
    try:
        return await session.get(Category, int(raw_id))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Kartlar
# ---------------------------------------------------------------------------


@router.message(Command("kartekle"))
async def add_card(message: Message, user: User, session: AsyncSession) -> None:
    arguments = _arguments(message)
    name, separator, days = (part.strip() for part in arguments.partition(NAME_SEPARATOR))
    parts = days.split()

    if not separator or not name or len(parts) != CARD_DAY_COUNT:
        await message.answer(messages.card_add_usage(), parse_mode="HTML")
        return

    try:
        statement_day, due_day = (int(part) for part in parts)
    except ValueError:
        await message.answer("Hesap kesim ve son ödeme günleri sayı olmalıdır.")
        return

    try:
        method = await settings_service.create_payment_method(
            session,
            user=user,
            name=name,
            type=TYPE_CREDIT_CARD,
            statement_day=statement_day,
            due_day=due_day,
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(
        f"✅ <b>{method.name}</b> eklendi (no: {method.id}).\n"
        f"Hesap kesim {statement_day}, son ödeme {due_day}.",
        parse_mode="HTML",
    )


@router.message(Command("kartad"))
async def rename_card(message: Message, user: User, session: AsyncSession) -> None:
    raw_id, _, new_name = _arguments(message).partition(" ")
    new_name = new_name.strip()
    if not raw_id or not new_name:
        await message.answer(
            "Kullanım: <code>/kartad &lt;no&gt; &lt;yeni ad&gt;</code>", parse_mode="HTML"
        )
        return

    method = await _find_card(session, raw_id)
    if method is None:
        await message.answer("Böyle bir ödeme yöntemi yok. ⚙️ Ayarlar'a bak.")
        return

    previous = method.name
    try:
        await settings_service.update_payment_method(
            session, user=user, method=method, changes={"name": new_name}
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(
        f"✅ <b>{previous}</b> → <b>{new_name}</b>\n\n"
        "Geçmiş harcamalar kaydedildikleri andaki kart adını göstermeye devam"
        " eder; rapor geçmişi değişmez.",
        parse_mode="HTML",
    )


@router.message(Command("kartgun"))
async def set_card_days_command(
    message: Message, user: User, session: AsyncSession
) -> None:
    parts = _arguments(message).split()
    if len(parts) != 3:
        await message.answer(
            "Kullanım: <code>/kartgun &lt;no&gt; &lt;kesim&gt; &lt;sonodeme&gt;</code>",
            parse_mode="HTML",
        )
        return
    try:
        method_id, statement_day, due_day = (int(part) for part in parts)
    except ValueError:
        await message.answer("Kart numarası ve günler sayı olmalıdır.")
        return

    method = await session.get(PaymentMethod, method_id)
    if method is None:
        await message.answer("Böyle bir ödeme yöntemi yok. ⚙️ Ayarlar'a bak.")
        return

    try:
        await settings_service.update_payment_method(
            session,
            user=user,
            method=method,
            changes={"statement_day": statement_day, "due_day": due_day},
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(
        f"✅ {method.name}: hesap kesim {statement_day}, son ödeme {due_day}.\n\n"
        + HISTORY_UNCHANGED_NOTE
    )


@router.message(Command("kartsil"))
async def delete_card(message: Message, user: User, session: AsyncSession) -> None:
    method = await _find_card(session, _arguments(message))
    if method is None:
        await message.answer(
            "Kullanım: <code>/kartsil &lt;no&gt;</code>", parse_mode="HTML"
        )
        return

    name = method.name
    try:
        await settings_service.delete_payment_method(session, user=user, method=method)
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}\n\n<code>/kartpasif {method.id}</code>", parse_mode="HTML")
        return

    await message.answer(f"🗑 <b>{name}</b> silindi.", parse_mode="HTML")


@router.message(Command("kartpasif"))
async def deactivate_card(message: Message, user: User, session: AsyncSession) -> None:
    await _toggle_card(message, user, session, active=False)


@router.message(Command("kartaktif"))
async def activate_card(message: Message, user: User, session: AsyncSession) -> None:
    await _toggle_card(message, user, session, active=True)


async def _toggle_card(
    message: Message, user: User, session: AsyncSession, *, active: bool
) -> None:
    method = await _find_card(session, _arguments(message))
    if method is None:
        await message.answer("Böyle bir ödeme yöntemi yok. ⚙️ Ayarlar'a bak.")
        return
    await settings_service.set_active(session, user=user, entity=method, active=active)
    state = "aktif edildi" if active else "pasife alındı"
    note = "" if active else "\n\nGeçmiş harcamalar ve raporlar etkilenmez."
    await message.answer(f"✅ <b>{method.name}</b> {state}.{note}", parse_mode="HTML")


# ---------------------------------------------------------------------------
# Kategoriler
# ---------------------------------------------------------------------------


@router.message(Command("kategori"))
async def list_categories_command(message: Message, session: AsyncSession) -> None:
    categories = await settings_service.list_categories(session, include_inactive=True)
    await message.answer(messages.category_list(categories), parse_mode="HTML")


@router.message(Command("kategoriekle"))
async def add_category(message: Message, user: User, session: AsyncSession) -> None:
    arguments = _arguments(message)
    if not arguments:
        await message.answer(messages.category_add_usage(), parse_mode="HTML")
        return

    # Ilk belirtec emoji ise ayrilir; degilse adin parcasi kabul edilir.
    first, _, rest = arguments.partition(" ")
    if rest and not first.isalnum() and len(first) <= 4:
        emoji, name = first, rest.strip()
    else:
        emoji, name = "", arguments

    try:
        category = await settings_service.create_category(
            session, user=user, name=name, emoji=emoji
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(
        f"✅ {category.emoji} <b>{category.name}</b> eklendi (no: {category.id}).",
        parse_mode="HTML",
    )


@router.message(Command("kategoriad"))
async def rename_category(message: Message, user: User, session: AsyncSession) -> None:
    raw_id, _, new_name = _arguments(message).partition(" ")
    new_name = new_name.strip()
    if not raw_id or not new_name:
        await message.answer(
            "Kullanım: <code>/kategoriad &lt;no&gt; &lt;yeni ad&gt;</code>",
            parse_mode="HTML",
        )
        return

    category = await _find_category(session, raw_id)
    if category is None:
        await message.answer("Böyle bir kategori yok. <code>/kategori</code> ile listele.", parse_mode="HTML")
        return

    previous = category.name
    try:
        await settings_service.update_category(
            session, user=user, category=category, changes={"name": new_name}
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(f"✅ <b>{previous}</b> → <b>{new_name}</b>", parse_mode="HTML")


@router.message(Command("kategorisil"))
async def delete_category_command(
    message: Message, user: User, session: AsyncSession
) -> None:
    category = await _find_category(session, _arguments(message))
    if category is None:
        await message.answer(
            "Kullanım: <code>/kategorisil &lt;no&gt;</code>", parse_mode="HTML"
        )
        return

    name = category.name
    try:
        await settings_service.delete_category(session, user=user, category=category)
    except settings_service.SettingsError as exc:
        await message.answer(
            f"⚠️ {exc}\n\n<code>/kategoripasif {category.id}</code>", parse_mode="HTML"
        )
        return

    await message.answer(f"🗑 <b>{name}</b> silindi.", parse_mode="HTML")


@router.message(Command("kategoripasif"))
async def deactivate_category(
    message: Message, user: User, session: AsyncSession
) -> None:
    await _toggle_category(message, user, session, active=False)


@router.message(Command("kategoriaktif"))
async def activate_category(message: Message, user: User, session: AsyncSession) -> None:
    await _toggle_category(message, user, session, active=True)


async def _toggle_category(
    message: Message, user: User, session: AsyncSession, *, active: bool
) -> None:
    category = await _find_category(session, _arguments(message))
    if category is None:
        await message.answer("Böyle bir kategori yok. <code>/kategori</code> ile listele.", parse_mode="HTML")
        return
    await settings_service.set_active(session, user=user, entity=category, active=active)
    state = "aktif edildi" if active else "pasife alındı"
    await message.answer(f"✅ <b>{category.name}</b> {state}.", parse_mode="HTML")
