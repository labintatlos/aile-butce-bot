"""Zamanlanmış hatırlatmaların içeriğine karar veren katman.

Bütçe takibinin asıl faydası, kullanıcı sormadan da konuşan bir sistemdir:
ekstre kesim günü, yaklaşan son ödeme ve dönem özetleri kimse bir düğmeye
basmayı akıl etmeden gelmelidir.

Bu modül yalnızca **ne gönderileceğine** karar verir; gönderme işi
`services/scheduler.py` içindedir. Karar tamamen deterministiktir ve dışarıdan
verilen `today` değerine dayanır, böylece gerçek saat beklenmeden test
edilebilir. Hiçbir tutar burada yeniden hesaplanmaz; hepsi mevcut rapor
fonksiyonlarından gelir.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category, Expense, User
from . import reports

KIND_STATEMENT_CUT = "statement_cut"
KIND_DUE_SOON = "due_soon"
KIND_DUE_TODAY = "due_today"
KIND_WEEKLY = "weekly_summary"
KIND_MONTHLY = "monthly_summary"

DEFAULT_DUE_REMINDER_DAYS = 3

_STATEMENT_LOOKBACK_DAYS = 75
"""Geçmişe kaç gün bakılacağı.

Son ödeme tarihi, ekstre kesiminden en fazla 60 gün sonra olabilir
(`ck_due_offset_in_range`). Bugün son ödemesi gelen bir ekstrenin kesim günü
bu kadar geride kalmış olabileceği için pencere biraz daha geniş tutulur.
"""


@dataclass(frozen=True, slots=True)
class CardNotice:
    """Bir karta ait ekstre veya son ödeme hatırlatması."""

    kind: str
    payment_method_id: int
    payment_method_name: str
    statement_date: date
    due_date: date
    total_minor: int
    installment_count: int
    days_until_due: int

    @property
    def key(self) -> str:
        """Aynı hatırlatmanın tekrar gönderilmesini engelleyen ayırt edici."""
        return f"{self.kind}:{self.payment_method_id}:{self.due_date.isoformat()}"


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    """Bir dönemin (hafta veya ay) harcama özeti."""

    kind: str
    start: date
    end: date
    total_minor: int
    transaction_count: int
    by_user: list[reports.NamedTotal] = field(default_factory=list)
    by_category: list[reports.NamedTotal] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.start.isoformat()}"


async def card_notices(
    session: AsyncSession,
    *,
    today: date,
    due_reminder_days: int = DEFAULT_DUE_REMINDER_DAYS,
) -> list[CardNotice]:
    """Bugün gönderilmesi gereken kart hatırlatmalarını üretir.

    Üç durum vardır ve hepsi aynı ekstre satırından türetilir: ekstre bugün
    kesiliyor, son ödemeye `due_reminder_days` gün kaldı, son ödeme bugün.
    """
    rows = await reports.upcoming_statements(
        session,
        since=today - timedelta(days=_STATEMENT_LOOKBACK_DAYS),
        # Son odeme her zaman kesimden sonradir; bugunden sonra kesilecek bir
        # ekstrenin bugune dusen son odemesi olamaz.
        until=today,
    )

    warning_day = today + timedelta(days=due_reminder_days)
    notices: list[CardNotice] = []
    for row in rows:
        for kind in _kinds_for(row, today=today, warning_day=warning_day):
            notices.append(
                CardNotice(
                    kind=kind,
                    payment_method_id=row.payment_method_id,
                    payment_method_name=row.payment_method_name,
                    statement_date=row.statement_date,
                    due_date=row.due_date,
                    total_minor=row.total_minor,
                    installment_count=row.installment_count,
                    days_until_due=(row.due_date - today).days,
                )
            )
    return notices


def _kinds_for(
    row: reports.StatementSummary, *, today: date, warning_day: date
) -> list[str]:
    kinds = []
    if row.statement_date == today:
        kinds.append(KIND_STATEMENT_CUT)
    if row.due_date == today:
        kinds.append(KIND_DUE_TODAY)
    elif row.due_date == warning_day:
        kinds.append(KIND_DUE_SOON)
    return kinds


# ---------------------------------------------------------------------------
# Dönem özetleri
# ---------------------------------------------------------------------------


def previous_week(today: date) -> tuple[date, date]:
    """Bir önceki pazartesi-pazar aralığı."""
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    return last_monday, last_monday + timedelta(days=6)


def previous_month(today: date) -> tuple[date, date]:
    """Bir önceki takvim ayının ilk ve son günü."""
    last_day_of_previous = today.replace(day=1) - timedelta(days=1)
    return last_day_of_previous.replace(day=1), last_day_of_previous


def due_period_summaries(today: date) -> list[tuple[str, date, date]]:
    """Bugün hangi dönem özetlerinin gönderileceğini söyler.

    Haftalık özet pazartesi, aylık özet ayın ilk günü gönderilir. İkisi de
    kapanmış bir dönemi anlatır; yarım bir haftanın veya ayın yanıltıcı
    toplamı hiçbir zaman gösterilmez.
    """
    windows = []
    if today.weekday() == calendar.MONDAY:
        start, end = previous_week(today)
        windows.append((KIND_WEEKLY, start, end))
    if today.day == 1:
        start, end = previous_month(today)
        windows.append((KIND_MONTHLY, start, end))
    return windows


async def period_summary(
    session: AsyncSession, *, kind: str, start: date, end: date
) -> PeriodSummary:
    """Verilen kapalı tarih aralığının harcama özetini çıkarır."""
    live = (
        Expense.deleted_at.is_(None),
        Expense.transaction_date >= start,
        Expense.transaction_date <= end,
    )

    total, count = (
        await session.execute(
            select(
                func.coalesce(func.sum(Expense.total_amount_minor), 0),
                func.count(Expense.id),
            ).where(*live)
        )
    ).one()

    by_user = [
        reports.NamedTotal(
            id=row.id,
            name=row.display_name,
            total_minor=row.total,
            transaction_count=row.count,
        )
        for row in (
            await session.execute(
                select(
                    User.id,
                    User.display_name,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0).label(
                        "total"
                    ),
                    func.count(Expense.id).label("count"),
                )
                .join(Expense, Expense.created_by_user_id == User.id)
                .where(*live)
                .group_by(User.id, User.display_name)
                .order_by(func.sum(Expense.total_amount_minor).desc())
            )
        ).all()
    ]

    by_category = [
        reports.NamedTotal(
            id=row.id,
            name=row.name,
            total_minor=row.total,
            transaction_count=row.count,
            emoji=row.emoji or "",
        )
        for row in (
            await session.execute(
                select(
                    Category.id,
                    Category.name,
                    Category.emoji,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0).label(
                        "total"
                    ),
                    func.count(Expense.id).label("count"),
                )
                .join(Expense, Expense.category_id == Category.id)
                .where(*live)
                .group_by(Category.id, Category.name, Category.emoji)
                .order_by(func.sum(Expense.total_amount_minor).desc())
            )
        ).all()
    ]

    return PeriodSummary(
        kind=kind,
        start=start,
        end=end,
        total_minor=total,
        transaction_count=count,
        by_user=by_user,
        by_category=by_category,
    )


async def period_summaries(
    session: AsyncSession, *, today: date
) -> list[PeriodSummary]:
    """Bugüne düşen dönem özetlerini üretir.

    Dönem boyunca hiç harcama yoksa özet gönderilmez: boş bir rapor bildirim
    olarak gelmeye değmez.
    """
    summaries = []
    for kind, start, end in due_period_summaries(today):
        summary = await period_summary(session, kind=kind, start=start, end=end)
        if summary.transaction_count:
            summaries.append(summary)
    return summaries
