"""Rapor mesajlarının metne dönüştürülmesi.

Saf fonksiyonlardır: rapor veri sınıflarını alır, Türkçe metin döndürür.
Telegram'a bağlı olmadıkları için doğrudan test edilebilirler.
"""

from __future__ import annotations

from ..services import reports
from .formatting import installment_label, long_date, money, month_name, short_date

EMPTY_MONTH = "Bu ay henüz harcama kaydı yok."
EMPTY_STATEMENTS = "Yaklaşan ekstre bulunmuyor."
EMPTY_PLANS = "Aktif taksitli alışveriş yok."

TOP_CATEGORY_LIMIT = 6


def monthly_report(report: reports.MonthlySpendingReport) -> str:
    """§20'deki aylık harcama özeti.

    Tutarlar harcama toplamıdır; taksitli bir alışveriş burada tam tutarıyla
    görünür. Kart ödeme yükü ayrı rapordadır.
    """
    if report.transaction_count == 0:
        return f"📊 {month_name(report.year, report.month)}\n\n{EMPTY_MONTH}"

    lines = [
        f"📊 {month_name(report.year, report.month)}",
        "",
        f"Toplam harcama: {money(report.total_minor)}",
        f"İşlem sayısı: {report.transaction_count}",
        "",
    ]

    for person in report.by_user:
        lines.append(f"👤 {person.name}: {money(person.total_minor)}")

    lines += [
        "",
        f"💵 Nakit: {money(report.cash_total_minor)}",
        f"💳 Kredi kartı: {money(report.card_total_minor)}",
    ]

    if report.by_category:
        lines += ["", "Kategoriler:"]
        for item in report.by_category[:TOP_CATEGORY_LIMIT]:
            label = f"{item.emoji} {item.name}".strip()
            lines.append(f"  {label}: {money(item.total_minor)}")

    if report.largest_expense is not None:
        biggest = report.largest_expense
        lines += [
            "",
            "En yüksek harcama:",
            f"  {money(biggest.total_amount_minor)}"
            + (f" — {biggest.description}" if biggest.description else ""),
        ]

    lines += [
        "",
        "ℹ️ Bu rapor harcama tutarlarını gösterir; taksitli alışverişler tam"
        " tutarıyla sayılır. Kart ödeme yükü için 💳 Ekstreler.",
    ]
    return "\n".join(lines)


def statements_report(rows: list[reports.StatementSummary]) -> str:
    """§21'deki kart bazlı ekstre listesi."""
    if not rows:
        return f"💳 Ekstreler\n\n{EMPTY_STATEMENTS}"

    lines = ["💳 Yaklaşan Ekstreler", ""]
    for row in rows:
        lines += [
            f"{row.payment_method_name}",
            f"  {long_date(row.statement_date)} ekstresi: {money(row.total_minor)}",
            f"  Son ödeme: {long_date(row.due_date)}",
            "",
        ]
    return "\n".join(lines).rstrip()


def installment_plans_report(plans: list[reports.ActiveInstallmentPlan]) -> str:
    """§22'deki aktif taksit listesi."""
    if not plans:
        return f"🧾 Taksitler\n\n{EMPTY_PLANS}"

    lines = ["🧾 Aktif Taksitler", ""]
    for plan in plans:
        title = plan.description or plan.category_name
        lines += [
            f"{title}",
            f"  Toplam: {money(plan.total_minor)}",
            f"  Taksit: {plan.paid_position}",
            f"  Kalan: {money(plan.remaining_minor)}",
            f"  Aylık yaklaşık: {money(plan.monthly_minor)}",
            f"  {plan.payment_method_name} · #{plan.public_id}",
            "",
        ]
    return "\n".join(lines).rstrip()


def obligations_report(
    months: list[reports.MonthlyObligation], *, basis_label: str
) -> str:
    """§23'teki gelecek ödeme yükü.

    Hangi bakışın gösterildiği başlıkta açıkça yazar: aynı borç ekstre ve son
    ödeme bakışlarında farklı aylara düşer.
    """
    lines = [f"📅 Yaklaşan Ödemeler ({basis_label})", ""]
    total = 0
    for row in months:
        total += row.total_minor
        lines.append(f"{month_name(row.year, row.month)}: {money(row.total_minor)}")
    lines += ["", f"Toplam: {money(total)}"]
    lines += [
        "",
        "ℹ️ Yalnızca kredi kartı taksitleri sayılır; nakit harcamalar ödenmiş"
        " kabul edilir.",
    ]
    return "\n".join(lines)


def quick_entry_needs_category(amount_minor: int) -> str:
    return (
        f"{money(amount_minor)} tutarını hangi kategoriye yazayım?"
    )


def quick_entry_help() -> str:
    return (
        "Hızlı kayıt için tutarla başlayan bir mesaj yazabilirsin:\n\n"
        "  <code>500 market</code>\n"
        "  <code>1.250,50 market Migros alışverişi</code>\n\n"
        "Ödeme yöntemi varsayılan olarak Nakit'tir; kaydettikten sonra"
        " kart seçebilirsin. Taksitli alışverişler için formu kullan."
    )


def deletion_prompt(public_id: str, total_minor: int) -> str:
    return (
        f"#{public_id} numaralı {money(total_minor)} tutarındaki harcamayı"
        " silmek istediğine emin misin?"
    )


def expense_summary_line(expense) -> str:
    """Arama ve liste sonuçlarında tek satırlık özet."""
    parts = [
        short_date(expense.transaction_date),
        money(expense.total_amount_minor),
        expense.payment_method_name_snapshot,
        installment_label(expense.installment_count),
    ]
    if expense.description:
        parts.append(expense.description)
    return " · ".join(parts)
