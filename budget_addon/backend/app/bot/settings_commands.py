"""Kart ve kategori yönetimi komutları.

Komut dilbilgisi bilinçli olarak basit ve deterministiktir; doğal dil
yorumlama yapılmaz. Adlar boşluk içerebildiği için, ad ile sayıların
karıştığı komutlarda `|` ayracı kullanılır.

    /kartekle Aykut Kredi Kartı 2 | 26
    /kartad 3 Yeni Kart Adı
    /kartgun 3 26
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

from ..config import Settings
from ..models.category import Category
from ..models.payment_method import TYPE_CREDIT_CARD, PaymentMethod
from ..models.user import User
from ..services import (
    budgets,
    cards,
    income,
    recurring,
    refunds,
    settings_service,
)
from ..services.expenses import get_expense
from ..services.finance.money import parse_amount_to_minor
from ..services.quick_entry import fold
from ..utils.time import local_today
from . import messages

logger = logging.getLogger(__name__)

router = Router()

NAME_SEPARATOR = "|"
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


STATEMENT_LABELS = ("kesim", "hesapkesim", "kesimgunu", "kesimgunu")
OFFSET_LABELS = ("vade", "gun", "gün", "sonodemefarki")


def parse_card_setup(text: str) -> tuple[int, int | None] | None:
    """Kart kurulum bilgisini okur.

    Kullanıcı yalnızca **hesap kesim gününü** girer; son ödeme tarihi ondan
    türetilir. İkinci bir sayı yazılırsa son ödemeye kaç gün kalacağını
    belirler (bankası farklı çalışan kullanıcılar için).

        "26"              -> (26, None)
        "kesim 26"        -> (26, None)
        "26 vade 12"      -> (26, 12)

    Anlaşılmayan girdide tahmin yürütülmez; `None` döner ve kullanıma dair
    açıklama gösterilir.
    """
    tokens = text.lower().split()
    if not tokens:
        return None

    statement_day: int | None = None
    offset_days: int | None = None
    positional: list[int] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if token in STATEMENT_LABELS and following and following.isdigit():
            statement_day = int(following)
            index += 2
            continue
        if token in OFFSET_LABELS and following and following.isdigit():
            offset_days = int(following)
            index += 2
            continue
        if token.isdigit():
            positional.append(int(token))
            index += 1
            continue
        return None

    if statement_day is None:
        if not positional:
            return None
        statement_day = positional.pop(0)
    if offset_days is None and positional:
        offset_days = positional.pop(0)
    if positional:
        return None
    return statement_day, offset_days


@router.message(Command("kartekle"))
async def add_card(message: Message, user: User, session: AsyncSession) -> None:
    arguments = _arguments(message)
    name, separator, days = (part.strip() for part in arguments.partition(NAME_SEPARATOR))

    if not separator or not name:
        await message.answer(messages.card_add_usage(), parse_mode="HTML")
        return

    parsed = parse_card_setup(days)
    if parsed is None:
        await message.answer(messages.card_add_usage(), parse_mode="HTML")
        return
    statement_day, offset_days = parsed

    try:
        method = await settings_service.create_payment_method(
            session,
            user=user,
            name=name,
            type=TYPE_CREDIT_CARD,
            statement_day=statement_day,
            **({"due_offset_days": offset_days} if offset_days else {}),
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(
        f"✅ <b>{method.name}</b> eklendi (no: {method.id}).\n\n"
        + messages.card_days_explained(method.statement_day, method.due_offset_days),
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
    raw_id, _, rest = _arguments(message).partition(" ")
    parsed = parse_card_setup(rest)
    if not raw_id.isdigit() or parsed is None:
        await message.answer(messages.card_days_usage(), parse_mode="HTML")
        return
    method_id = int(raw_id)
    statement_day, offset_days = parsed

    method = await session.get(PaymentMethod, method_id)
    if method is None:
        await message.answer("Böyle bir ödeme yöntemi yok. ⚙️ Ayarlar'a bak.")
        return

    try:
        await settings_service.update_payment_method(
            session,
            user=user,
            method=method,
            changes={
                "statement_day": statement_day,
                **({"due_offset_days": offset_days} if offset_days else {}),
            },
        )
    except settings_service.SettingsError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await message.answer(
        f"✅ <b>{method.name}</b> güncellendi.\n\n"
        + messages.card_days_explained(method.statement_day, method.due_offset_days)
        + "\n\n"
        + HISTORY_UNCHANGED_NOTE,
        parse_mode="HTML",
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


# ---------------------------------------------------------------------------
# Hatırlatmalar
# ---------------------------------------------------------------------------


@router.message(Command("hatirlatici"))
async def reminder_status(
    message: Message, user: User, settings: Settings
) -> None:
    await message.answer(
        messages.reminder_status(
            enabled=user.reminders_enabled,
            hour=settings.reminder_hour,
            days_before_due=settings.due_reminder_days,
        ),
        parse_mode="HTML",
    )


@router.message(Command("hatirlaticiac"))
async def enable_reminders(message: Message, user: User, session: AsyncSession) -> None:
    await _set_reminders(message, user, session, enabled=True)


@router.message(Command("hatirlaticikapat"))
async def disable_reminders(
    message: Message, user: User, session: AsyncSession
) -> None:
    await _set_reminders(message, user, session, enabled=False)


async def _set_reminders(
    message: Message, user: User, session: AsyncSession, *, enabled: bool
) -> None:
    user.reminders_enabled = enabled
    await session.commit()
    state = "açıldı" if enabled else "kapatıldı"
    await message.answer(f"🔔 Hatırlatmalar {state}.")


# ---------------------------------------------------------------------------
# Sabit giderler
# ---------------------------------------------------------------------------

RECURRING_FIELD_COUNT = 5


def _match_by_name(needle: str, items):
    """Ada göre tam veya tekil önek eşleşmesi arar.

    Hızlı girişteki kuralın aynısı: birden fazla adaya uyan bir metin kabul
    edilmez, çünkü hangisinin kastedildiğini tahmin etmek kullanıcının
    parasıyla kumar oynamaktır.
    """
    folded = fold(needle.strip())
    if not folded:
        return None
    exact = [item for item in items if fold(item.name) == folded]
    if len(exact) == 1:
        return exact[0]
    prefixed = [item for item in items if fold(item.name).startswith(folded)]
    return prefixed[0] if len(prefixed) == 1 else None


@router.message(Command("sabit"))
async def list_recurring(message: Message, session: AsyncSession) -> None:
    templates = await recurring.list_templates(session, include_inactive=True)
    categories = {c.id: c for c in await settings_service.list_categories(session, include_inactive=True)}
    methods = {m.id: m for m in await settings_service.list_payment_methods(session, include_inactive=True)}
    await message.answer(
        messages.recurring_list(templates, categories=categories, methods=methods),
        parse_mode="HTML",
    )


@router.message(Command("sabitekle"))
async def add_recurring(
    message: Message, user: User, session: AsyncSession, settings: Settings
) -> None:
    arguments = _arguments(message)
    parts = [part.strip() for part in arguments.split(NAME_SEPARATOR)]
    if len(parts) != RECURRING_FIELD_COUNT:
        await message.answer(messages.recurring_add_usage(), parse_mode="HTML")
        return

    name, raw_amount, raw_day, raw_category, raw_method = parts
    if not raw_day.isdigit():
        await message.answer("Gün yalnızca rakamlardan oluşmalı. Örnek: 1")
        return

    category = _match_by_name(
        raw_category, await settings_service.list_categories(session)
    )
    if category is None:
        await message.answer(
            f"'{raw_category}' kategorisi bulunamadı. Listeyi görmek için /kategori"
        )
        return

    method = _match_by_name(
        raw_method, await settings_service.list_payment_methods(session)
    )
    if method is None:
        await message.answer(f"'{raw_method}' ödeme yöntemi bulunamadı.")
        return

    try:
        template = await recurring.create_template(
            session,
            user=user,
            name=name,
            category_id=category.id,
            payment_method_id=method.id,
            amount=raw_amount,
            day_of_month=int(raw_day),
            start_date=local_today(settings.timezone),
        )
    except (recurring.RecurringError, ValueError) as error:
        await message.answer(f"⚠️ {error}")
        return

    await message.answer(
        messages.recurring_created_template(template, method_name=method.name),
        parse_mode="HTML",
    )


async def _load_template(message: Message, session: AsyncSession, raw_id: str):
    try:
        template = await recurring.get_template(session, int(raw_id))
    except ValueError:
        template = None
    if template is None:
        await message.answer("Böyle bir sabit gider yok. Listeyi görmek için /sabit")
    return template


@router.message(Command("sabittutar"))
async def change_recurring_amount(
    message: Message, user: User, session: AsyncSession
) -> None:
    raw_id, _, raw_amount = _arguments(message).partition(" ")
    template = await _load_template(message, session, raw_id)
    if template is None:
        return
    try:
        amount_minor = parse_amount_to_minor(raw_amount.strip())
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    await recurring.update_template(
        session, user=user, template=template, amount_minor=amount_minor
    )
    await message.answer(
        f"✅ <b>{template.name}</b> tutarı {messages.money(amount_minor)} oldu."
        "\n\nGeçmiş aylarda kaydedilmiş tutarlar değişmedi.",
        parse_mode="HTML",
    )


@router.message(Command("sabitgun"))
async def change_recurring_day(
    message: Message, user: User, session: AsyncSession
) -> None:
    raw_id, _, raw_day = _arguments(message).partition(" ")
    template = await _load_template(message, session, raw_id)
    if template is None:
        return
    if not raw_day.strip().isdigit():
        await message.answer("Gün yalnızca rakamlardan oluşmalı. Örnek: /sabitgun 3 15")
        return

    try:
        await recurring.update_template(
            session, user=user, template=template, day_of_month=int(raw_day)
        )
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await message.answer(
        f"✅ <b>{template.name}</b> artık her ayın {template.day_of_month}. günü"
        " kaydedilecek.",
        parse_mode="HTML",
    )


@router.message(Command("sabitsil"))
async def delete_recurring(message: Message, user: User, session: AsyncSession) -> None:
    template = await _load_template(message, session, _arguments(message))
    if template is None:
        return
    name = template.name
    await recurring.delete_template(session, user=user, template=template)
    await message.answer(
        f"🗑 <b>{name}</b> sabit giderlerden çıkarıldı."
        "\n\nDaha önce kaydedilmiş harcamalar duruyor.",
        parse_mode="HTML",
    )


@router.message(Command("sabitpasif"))
async def deactivate_recurring(
    message: Message, user: User, session: AsyncSession
) -> None:
    await _toggle_recurring(message, user, session, active=False)


@router.message(Command("sabitaktif"))
async def activate_recurring(
    message: Message, user: User, session: AsyncSession
) -> None:
    await _toggle_recurring(message, user, session, active=True)


async def _toggle_recurring(
    message: Message, user: User, session: AsyncSession, *, active: bool
) -> None:
    template = await _load_template(message, session, _arguments(message))
    if template is None:
        return
    await recurring.update_template(
        session, user=user, template=template, is_active=active
    )
    state = "aktif edildi" if active else "durduruldu"
    await message.answer(f"✅ <b>{template.name}</b> {state}.", parse_mode="HTML")


# ---------------------------------------------------------------------------
# Bütçe hedefleri
# ---------------------------------------------------------------------------


@router.message(Command("butce"))
async def show_budgets(
    message: Message, session: AsyncSession, settings: Settings
) -> None:
    today = local_today(settings.timezone)
    statuses = await budgets.monthly_status(
        session, year=today.year, month=today.month
    )
    await message.answer(messages.budget_list(statuses), parse_mode="HTML")


@router.message(Command("butceayarla"))
async def set_budget(message: Message, user: User, session: AsyncSession) -> None:
    raw_name, separator, raw_amount = _arguments(message).partition(NAME_SEPARATOR)
    if not separator:
        await message.answer(
            "<b>Kategori hedefi</b>\n\n"
            "<code>/butceayarla Market | 4000</code>\n\n"
            "Hedefi kaldırmak için: <code>/butcesil Market</code>",
            parse_mode="HTML",
        )
        return

    category = _match_by_name(
        raw_name, await settings_service.list_categories(session)
    )
    if category is None:
        await message.answer(
            f"'{raw_name.strip()}' kategorisi bulunamadı. Listeyi görmek için /kategori"
        )
        return
    try:
        amount_minor = parse_amount_to_minor(raw_amount.strip())
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    await settings_service.update_category(
        session,
        user=user,
        category=category,
        changes={"monthly_budget_minor": amount_minor},
    )
    await message.answer(
        f"🎯 <b>{category.name}</b> için aylık hedef {messages.money(amount_minor)}"
        " olarak ayarlandı.",
        parse_mode="HTML",
    )


@router.message(Command("butcesil"))
async def clear_budget(message: Message, user: User, session: AsyncSession) -> None:
    category = _match_by_name(
        _arguments(message), await settings_service.list_categories(session)
    )
    if category is None:
        await message.answer("Böyle bir kategori yok. Listeyi görmek için /kategori")
        return

    await settings_service.update_category(
        session, user=user, category=category, changes={"monthly_budget_minor": None}
    )
    await message.answer(
        f"🎯 <b>{category.name}</b> hedefi kaldırıldı.", parse_mode="HTML"
    )


# ---------------------------------------------------------------------------
# Gelirler
# ---------------------------------------------------------------------------


@router.message(Command("gelir"))
async def add_income(
    message: Message, user: User, session: AsyncSession, settings: Settings
) -> None:
    arguments = _arguments(message)
    if not arguments:
        await message.answer(messages.income_add_usage(), parse_mode="HTML")
        return

    raw_amount, _, source = arguments.partition(" ")
    try:
        record = await income.create_income(
            session,
            user=user,
            amount=raw_amount,
            received_date=local_today(settings.timezone),
            source=source.strip() or income.DEFAULT_SOURCE,
        )
    except ValueError as error:
        await message.answer(f"⚠️ {error}\n\n{messages.income_add_usage()}", parse_mode="HTML")
        return

    await message.answer(
        f"💰 <b>{record.source}</b> kaydedildi: {messages.money(record.amount_minor)}"
        "\n\nAy sonunda ne kalacağını görmek için 💰 Durum",
        parse_mode="HTML",
    )


@router.message(Command("gelirler"))
async def list_incomes(
    message: Message, session: AsyncSession, settings: Settings
) -> None:
    today = local_today(settings.timezone)
    records = await income.list_incomes(session, year=today.year, month=today.month)
    await message.answer(messages.income_list(records), parse_mode="HTML")


@router.message(Command("gelirsil"))
async def delete_income(message: Message, user: User, session: AsyncSession) -> None:
    raw_id = _arguments(message)
    try:
        record = await income.get_income(session, int(raw_id))
    except ValueError:
        record = None
    if record is None:
        await message.answer("Böyle bir gelir kaydı yok. Listelemek için /gelirler")
        return

    await income.soft_delete_income(session, user=user, record=record)
    await message.answer(f"🗑 <b>{record.source}</b> silindi.", parse_mode="HTML")


# ---------------------------------------------------------------------------
# Kart limitleri
# ---------------------------------------------------------------------------


@router.message(Command("kartlimit"))
async def set_card_limit(message: Message, user: User, session: AsyncSession) -> None:
    raw_id, _, raw_amount = _arguments(message).partition(" ")
    method = await _find_card(session, raw_id)
    if method is None or method.type != TYPE_CREDIT_CARD:
        await message.answer(
            "<b>Kart limiti</b>\n\n"
            "<code>/kartlimit 3 50000</code>\n\n"
            "Kart numaralarını görmek için ⚙️ Ayarlar",
            parse_mode="HTML",
        )
        return

    try:
        limit_minor = parse_amount_to_minor(raw_amount.strip())
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    await settings_service.update_payment_method(
        session,
        user=user,
        method=method,
        changes={"credit_limit_minor": limit_minor},
    )
    await message.answer(
        f"💳 <b>{method.name}</b> limiti {messages.money(limit_minor)} olarak"
        " ayarlandı.\n\nDurumu görmek için /kartlar",
        parse_mode="HTML",
    )


@router.message(Command("kartlar"))
async def show_card_usage(message: Message, session: AsyncSession) -> None:
    usages = await cards.card_usage(session)
    await message.answer(messages.card_usage_list(usages), parse_mode="HTML")


# ---------------------------------------------------------------------------
# İadeler
# ---------------------------------------------------------------------------


def _expense_id_from(raw: str) -> int | None:
    """`184` ya da `EXP-000184` biçimindeki kimliği sayıya çevirir."""
    cleaned = raw.strip().upper().removeprefix("#").removeprefix("EXP-")
    return int(cleaned) if cleaned.isdigit() else None


@router.message(Command("iade"))
async def add_refund(
    message: Message, user: User, session: AsyncSession, settings: Settings
) -> None:
    raw_id, _, raw_amount = _arguments(message).partition(" ")
    expense_id = _expense_id_from(raw_id)
    if expense_id is None or not raw_amount.strip():
        await message.answer(messages.refund_usage(), parse_mode="HTML")
        return

    try:
        refund = await refunds.create_refund(
            session,
            user=user,
            expense_id=expense_id,
            amount=raw_amount.strip(),
            refund_date=local_today(settings.timezone),
        )
    except (refunds.RefundError, ValueError) as error:
        await message.answer(f"⚠️ {error}")
        return

    expense = await get_expense(session, expense_id)
    remaining = expense.total_amount_minor - await refunds.refunded_total(
        session, expense_id
    )
    await message.answer(
        messages.refund_receipt(
            refund=refund,
            expense_public_id=expense.public_id,
            remaining_minor=remaining,
        ),
        parse_mode="HTML",
    )
