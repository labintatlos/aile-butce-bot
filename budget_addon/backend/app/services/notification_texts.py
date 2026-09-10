"""Bildirim metinleri.

Hangi hatırlatmanın ne zaman gideceğine `reminders`, `budgets` ve `cards`
servisleri karar verir; burada yalnızca başlık ve gövdeye dönüştürülür. Aynı
metin site içinde, e-postada ve telefondaki anlık bildirimde kullanıldığı için
biçimlendirme işareti içermez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..utils.formatting import long_date, money, month_name, short_date
from . import reminders

KIND_RECURRING_CREATED = "recurring_created"
KIND_BUDGET_ALERT = "budget_alert"
KIND_CARD_LIMIT = "card_limit"
KIND_TEST = "test"

TOP_CATEGORY_LIMIT = 6

LINK_NOTIFICATIONS = "bildirimler"
LINK_REPORTS = "raporlar"
LINK_RECURRING = "sabit"


@dataclass(frozen=True, slots=True)
class NotificationText:
    kind: str
    key: str
    """Aynı bildirimin aynı kişiye ikinci kez gitmesini engelleyen ayırt edici."""
    title: str
    body: str
    link: str | None = None


CARD_HEADINGS = {
    reminders.KIND_STATEMENT_CUT: "Bugün ekstre kesiliyor",
    reminders.KIND_DUE_TODAY: "Bugün son ödeme günü",
    reminders.KIND_DUE_SOON: "Son ödeme yaklaşıyor",
}


def card_notice(notice: reminders.CardNotice) -> NotificationText:
    """Ekstre kesimi ve son ödeme hatırlatması."""
    if notice.kind == reminders.KIND_STATEMENT_CUT:
        due = f"Son ödeme: {long_date(notice.due_date)}"
    elif notice.kind == reminders.KIND_DUE_SOON:
        due = (
            f"Son ödeme: {long_date(notice.due_date)}"
            f" ({notice.days_until_due} gün kaldı)"
        )
    else:
        due = f"Son ödeme: bugün, {long_date(notice.due_date)}"
    return NotificationText(
        kind=notice.kind,
        key=notice.key,
        title=f"{CARD_HEADINGS[notice.kind]}: {notice.payment_method_name}",
        body="\n".join(
            [
                f"{money(notice.total_minor)} · {notice.installment_count} taksit kalemi",
                due,
            ]
        ),
        link=LINK_REPORTS,
    )


def period_summary(summary: reminders.PeriodSummary) -> NotificationText:
    """Haftalık ve aylık kapanış özeti."""
    if summary.kind == reminders.KIND_WEEKLY:
        title = f"Geçen hafta: {short_date(summary.start)} – {short_date(summary.end)}"
    else:
        title = f"{month_name(summary.start.year, summary.start.month)} kapanışı"

    lines = [
        f"Toplam harcama: {money(summary.total_minor)} ({summary.transaction_count} işlem)"
    ]
    lines += [f"{person.name}: {money(person.total_minor)}" for person in summary.by_user]
    if summary.by_category:
        lines.append("Kategoriler:")
        lines += [
            f"  {f'{item.emoji} {item.name}'.strip()}: {money(item.total_minor)}"
            for item in summary.by_category[:TOP_CATEGORY_LIMIT]
        ]
    return NotificationText(
        kind=summary.kind,
        key=summary.key,
        title=title,
        body="\n".join(lines),
        link=LINK_REPORTS,
    )


def recurring_created(
    *, name: str, amount_minor: int, when: date, public_id: str
) -> NotificationText:
    """Sabit giderin kendiliğinden kaydedildiği haberi."""
    return NotificationText(
        kind=KIND_RECURRING_CREATED,
        key=f"{KIND_RECURRING_CREATED}:{public_id}",
        title=f"Sabit gider kaydedildi: {name}",
        body="\n".join(
            [
                f"{money(amount_minor)} · {long_date(when)}",
                f"İşlem #{public_id}. Tutar değiştiyse kaydı düzenleyebilirsiniz.",
            ]
        ),
        link=LINK_RECURRING,
    )


def budget_alert(alert) -> NotificationText:
    """Eşiği geçen kategori bütçesi."""
    status = alert.status
    label = f"{status.emoji} {status.name}".strip()
    if status.is_exceeded:
        title = f"Bütçe aşıldı: {status.name}"
        closing = f"{money(status.overspend_minor)} hedefin üzerinde."
    else:
        title = f"Bütçenin sonuna yaklaşıldı: {status.name}"
        closing = f"Kalan: {money(status.remaining_minor)}"
    return NotificationText(
        kind=KIND_BUDGET_ALERT,
        key=alert.key,
        title=title,
        body="\n".join(
            [
                f"{label} — {month_name(status.year, status.month)}",
                f"{money(status.spent_minor)} / {money(status.budget_minor)} (%{status.ratio})",
                closing,
            ]
        ),
        link=LINK_REPORTS,
    )


def card_limit_alert(alert) -> NotificationText:
    """Limiti dolmaya yaklaşan veya aşılan kart."""
    usage = alert.usage
    if usage.is_over_limit:
        title = f"Kart limiti aşıldı: {usage.name}"
        closing = (
            f"{money(usage.outstanding_minor - usage.credit_limit_minor)} limitin üzerinde."
        )
    else:
        title = f"Kart limiti dolmak üzere: {usage.name}"
        closing = f"Kullanılabilir: {money(usage.available_minor)}"
    return NotificationText(
        kind=KIND_CARD_LIMIT,
        key=alert.key,
        title=title,
        body="\n".join(
            [
                f"{money(usage.outstanding_minor)} / {money(usage.credit_limit_minor)} (%{usage.ratio})",
                closing,
            ]
        ),
        link=LINK_REPORTS,
    )
