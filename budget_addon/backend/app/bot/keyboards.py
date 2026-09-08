"""Telegram klavyeleri ve buton verileri.

Callback verileri sabit önekler kullanır; elle yazılmış dizeler yerine
buradaki yardımcılar çağrılır ki bir yerde değişince her yer değişsin.
"""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

BUTTON_ADD = "➕ Harcama Ekle"
BUTTON_MONTH = "📊 Bu Ay"
BUTTON_STATEMENTS = "💳 Ekstreler"
BUTTON_INSTALLMENTS = "🧾 Taksitler"
BUTTON_UPCOMING = "📅 Yaklaşan Ödemeler"
BUTTON_ANALYSIS = "📈 Analiz"
BUTTON_SEARCH = "🔎 Harcama Ara"
BUTTON_SETTINGS = "⚙️ Ayarlar"

MENU_LAYOUT = (
    (BUTTON_ADD,),
    (BUTTON_MONTH, BUTTON_STATEMENTS),
    (BUTTON_INSTALLMENTS, BUTTON_UPCOMING),
    (BUTTON_ANALYSIS, BUTTON_SEARCH),
    (BUTTON_SETTINGS,),
)

CALLBACK_EDIT = "expense:edit"
CALLBACK_DELETE = "expense:delete"
CALLBACK_DELETE_CONFIRM = "expense:delete:yes"
CALLBACK_DELETE_CANCEL = "expense:delete:no"
CALLBACK_CATEGORY = "quick:category"
CALLBACK_PAYMENT = "quick:payment"

BASIS_STATEMENT_LABEL = "Ekstre Bazlı"
BASIS_DUE_LABEL = "Son Ödeme Bazlı"


def main_menu(webapp_url: str | None) -> ReplyKeyboardMarkup:
    """Ana menü.

    `webapp_url` yapılandırılmamışsa `➕ Harcama Ekle` normal bir düğme olarak
    kalır ve kullanıcıya hızlı metin girişi anlatılır; Mini App adresi
    olmadan da bot tam işlevlidir.
    """
    rows = []
    for row in MENU_LAYOUT:
        buttons = []
        for label in row:
            if label == BUTTON_ADD and webapp_url:
                buttons.append(
                    KeyboardButton(text=label, web_app=WebAppInfo(url=webapp_url))
                )
            else:
                buttons.append(KeyboardButton(text=label))
        rows.append(buttons)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def expense_actions(expense_id: int) -> InlineKeyboardMarkup:
    """§18'deki kayıt mesajının altındaki düzenle/sil düğmeleri."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Düzenle", callback_data=f"{CALLBACK_EDIT}:{expense_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 Sil", callback_data=f"{CALLBACK_DELETE}:{expense_id}"
                ),
            ]
        ]
    )


def delete_confirmation(expense_id: int) -> InlineKeyboardMarkup:
    """Silme geri alınabilir olsa da onay sorulur (§27)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Evet, sil",
                    callback_data=f"{CALLBACK_DELETE_CONFIRM}:{expense_id}",
                ),
                InlineKeyboardButton(
                    text="Vazgeç",
                    callback_data=f"{CALLBACK_DELETE_CANCEL}:{expense_id}",
                ),
            ]
        ]
    )


def category_choices(categories, *, per_row: int = 2) -> InlineKeyboardMarkup:
    """Hızlı girişte kategori belirsizse gösterilen seçim klavyesi."""
    buttons = [
        InlineKeyboardButton(
            text=f"{category.emoji} {category.name}".strip(),
            callback_data=f"{CALLBACK_CATEGORY}:{category.id}",
        )
        for category in categories
    ]
    rows = [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_choices(methods, *, per_row: int = 1) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=method.name, callback_data=f"{CALLBACK_PAYMENT}:{method.id}"
        )
        for method in methods
    ]
    rows = [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_callback(data: str, prefix: str) -> int | None:
    """`expense:delete:12` -> 12. Eşleşmezse `None`."""
    marker = f"{prefix}:"
    if not data.startswith(marker):
        return None
    try:
        return int(data[len(marker) :])
    except ValueError:
        return None
