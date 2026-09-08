"""Telegram mesajlarının Türkçe biçimlendirilmesi.

Tüm kullanıcı arayüzü Türkçedir. Biçimlendirme tek yerde toplanır ki bot
mesajları, Mini App ve raporlar aynı sayıyı aynı şekilde göstersin.
"""

from __future__ import annotations

from datetime import date

from ..services.finance.money import format_try

MONTH_NAMES = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

INSTALLMENT_LABEL_SINGLE = "Peşin"


def money(minor: int) -> str:
    """`12.450,75 TL`"""
    return format_try(minor)


def short_date(value: date) -> str:
    """`02.09.2026` — listelerde ve tablolarda."""
    return value.strftime("%d.%m.%Y")


def long_date(value: date) -> str:
    """`2 Eylül 2026` — okunabilir mesajlarda."""
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def month_name(year: int, month: int) -> str:
    """`Eylül 2026`"""
    return f"{MONTH_NAMES[month - 1]} {year}"


def installment_label(count: int) -> str:
    """`Peşin` veya `3 Taksit`."""
    return INSTALLMENT_LABEL_SINGLE if count <= 1 else f"{count} Taksit"


def expense_receipt(
    *,
    public_id: str,
    category_name: str,
    category_emoji: str,
    description: str | None,
    total_minor: int,
    payment_method_name: str,
    installment_count: int,
    first_statement_date: date | None,
    is_credit_card: bool,
) -> str:
    """§18'deki kayıt onay mesajı."""
    lines = [
        "✅ Harcama kaydedildi",
        "",
        f"{category_emoji} {category_name}".strip(),
    ]
    if description:
        lines.append(description)
    lines += [
        "",
        "Tutar:",
        money(total_minor),
        "",
        "Ödeme:",
        payment_method_name,
        "",
        "Taksit:",
        installment_label(installment_count),
    ]
    if is_credit_card and first_statement_date is not None:
        lines += ["", "İlk ekstre:", long_date(first_statement_date)]
    lines += ["", "İşlem:", f"#{public_id}"]
    return "\n".join(lines)
