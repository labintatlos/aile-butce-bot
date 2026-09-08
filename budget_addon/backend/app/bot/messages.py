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


def search_help() -> str:
    return (
        "🔎 <b>Harcama Ara</b>\n\n"
        "Aramak için <code>ara</code> ile başlayan bir mesaj yaz:\n\n"
        "  <code>ara migros</code>\n"
        "  <code>ara EXP-000184</code>\n\n"
        "Açıklama ve işlem numarası üzerinde arama yapılır."
    )


def search_results(page, *, term: str) -> str:
    if page.total == 0:
        return f"🔎 <b>{term}</b> için sonuç bulunamadı."

    lines = [f"🔎 <b>{term}</b> — {page.total} sonuç", ""]
    for expense in page.items:
        lines.append(f"#{expense.public_id} · {expense_summary_line(expense)}")
    if page.has_next:
        lines += ["", f"İlk {len(page.items)} sonuç gösteriliyor."]
    return "\n".join(lines)


def settings_overview(methods, categories) -> str:
    """Kart ve kategori ayarlarının özeti ve nasıl düzeltileceği."""
    lines = ["⚙️ <b>Ayarlar</b>", "", "<b>Ödeme yöntemleri</b>"]
    for method in methods:
        if method.type == "cash":
            lines.append(f"  {method.id}. {method.name} — nakit")
        else:
            lines.append(
                f"  {method.id}. {method.name} — kesim {method.statement_day},"
                f" son ödeme +{method.due_offset_days} gün"
            )
    lines += [
        "",
        "<code>/kartekle Kart Adı | 26</code>",
        "<code>/kartad &lt;no&gt; &lt;yeni ad&gt;</code>",
        "<code>/kartgun &lt;no&gt; &lt;kesim günü&gt;</code>",
        "<code>/kartsil &lt;no&gt;</code>",
        "<code>/kartpasif &lt;no&gt;</code> · <code>/kartaktif &lt;no&gt;</code>",
        "",
        f"<b>Kategoriler</b> ({len(categories)} aktif)",
        "  " + ", ".join(c.name for c in categories[:8])
        + (" …" if len(categories) > 8 else ""),
        "",
        "<code>/kategori</code> ile listele ve düzenle",
        "",
        "ℹ️ Yalnızca hesap kesim günü girilir; son ödeme tarihi ondan"
        " hesaplanır ve hafta sonuna denk gelirse pazartesiye taşınır.",
        "ℹ️ Kart ayarını değiştirmek geçmiş harcamaların taksit planını"
        " <b>değiştirmez</b>; yeni ayar yalnızca sonraki harcamalara uygulanır.",
        "ℹ️ Harcamada kullanılan bir kart veya kategori silinemez; pasife"
        " alınır. Böylece geçmiş raporlar okunabilir kalır.",
    ]
    return "\n".join(lines)


def analysis_report(report, previous) -> str:
    """Kategori dağılımı ve önceki aya göre değişim."""
    lines = [f"📈 <b>Analiz</b> — {month_name(report.year, report.month)}", ""]
    if report.transaction_count == 0:
        return "\n".join(lines) + EMPTY_MONTH

    lines.append(f"Toplam: {money(report.total_minor)}")
    if previous is not None and previous.total_minor:
        change = report.total_minor - previous.total_minor
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "▬")
        percent = round(abs(change) * 100 / previous.total_minor)
        lines.append(
            f"Önceki aya göre: {arrow} {money(abs(change))} (%{percent})"
        )
    lines.append("")

    total = report.total_minor or 1
    for item in report.by_category:
        share = round(item.total_minor * 100 / total)
        label = f"{item.emoji} {item.name}".strip()
        lines.append(f"  {label}: {money(item.total_minor)} (%{share})")
    return "\n".join(lines)


def expense_detail(expense) -> str:
    lines = [
        f"#{expense.public_id}",
        "",
        f"{expense.category.emoji} {expense.category.name}".strip(),
    ]
    if expense.description:
        lines.append(expense.description)
    lines += [
        "",
        f"Tutar: {money(expense.total_amount_minor)}",
        f"Ödeme: {expense.payment_method_name_snapshot}",
        f"Taksit: {installment_label(expense.installment_count)}",
        f"Tarih: {long_date(expense.transaction_date)}",
        "",
        "Kategoriyi aşağıdan değiştirebilirsin. Tutar, tarih, kart veya taksit"
        " sayısını değiştirmek taksit planını yeniden kurar; bunun için formu"
        " kullan.",
    ]
    return "\n".join(lines)


def card_add_usage() -> str:
    return (
        "🆕 <b>Kart ekle</b>\n\n"
        "  <code>/kartekle Aykut Kredi Kartı 2 | 26</code>\n\n"
        "Tek sayı yeter: kartın <b>hesap kesim günü</b>, yani ekstrenin"
        " kesildiği ayın günü. Son ödeme tarihi bundan otomatik hesaplanır.\n\n"
        "Bankan farklı çalışıyorsa vadeyi de yazabilirsin:\n"
        "  <code>/kartekle Kart Adı | 26 vade 12</code>\n\n"
        "Ayraç (<code>|</code>) gerekiyor çünkü kart adları boşluk içerebiliyor."
    )


def card_days_usage() -> str:
    return (
        "📅 <b>Hesap kesim gününü düzelt</b>\n\n"
        "  <code>/kartgun 2 26</code>\n\n"
        "Sadece hesap kesim gününü yaz; son ödeme tarihi ondan hesaplanır.\n\n"
        "Vadeyi değiştirmek istersen: <code>/kartgun 2 26 vade 12</code>\n"
        "Kart numaralarını ⚙️ Ayarlar ekranında görebilirsin."
    )


def card_days_explained(statement_day: int, offset_days: int) -> str:
    """Kaydedilen ayarın ne anlama geldiğini düz cümleyle gösterir."""
    return (
        f"Her ayın <b>{statement_day}</b>. günü ekstre kesilir, son ödeme"
        f" tarihi <b>{offset_days} gün sonrasıdır</b>.\n"
        "Hafta sonuna denk gelirse pazartesiye taşınır."
    )


def category_add_usage() -> str:
    return (
        "Kategori eklemek için:\n\n"
        "  <code>/kategoriekle 🎬 Sinema</code>\n"
        "  <code>/kategoriekle Abonelikler</code>\n\n"
        "Emoji isteğe bağlıdır."
    )


def category_list(categories) -> str:
    lines = ["🗂 <b>Kategoriler</b>", ""]
    for category in categories:
        mark = "" if category.is_active else "  (pasif)"
        label = f"{category.emoji} {category.name}".strip()
        lines.append(f"  {category.id}. {label}{mark}")
    lines += [
        "",
        "<code>/kategoriekle 🎬 Sinema</code>",
        "<code>/kategoriad &lt;no&gt; &lt;yeni ad&gt;</code>",
        "<code>/kategorisil &lt;no&gt;</code>",
        "<code>/kategoripasif &lt;no&gt;</code> · <code>/kategoriaktif &lt;no&gt;</code>",
    ]
    return "\n".join(lines)
