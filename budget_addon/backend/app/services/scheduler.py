"""Günlük işler: sabit gider üretimi ve hatırlatmalar.

Ayrı bir zamanlayıcı kütüphanesi kullanılmaz: tek bir asenkron döngü dakikada
bir uyanır, yerel saat hatırlatma saatine geldiyse günün işlerini yapar. Saat
dilimi tamamen `settings.timezone` üzerinden yönetilir.

Tekrarlı bildirim döngüyle değil veritabanıyla engellenir (bkz.
`notifications.notify`): eklenti gün içinde on kez yeniden başlasa da aynı
hatırlatma ikinci kez oluşturulmaz.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import User
from ..utils.time import local_now
from . import budgets, cards, notifications, recurring, reminders
from . import notification_texts as texts

logger = logging.getLogger(__name__)

TICK_SECONDS = 60


async def _recipients(session: AsyncSession) -> list[User]:
    return list(
        (
            await session.scalars(
                select(User)
                .where(User.is_active.is_(True), User.reminders_enabled.is_(True))
                .order_by(User.id)
            )
        ).all()
    )


async def pending_messages(
    session: AsyncSession, settings: Settings, *, today: date
) -> list[texts.NotificationText]:
    """Bugüne düşen hatırlatmalar. Kişiden bağımsızdır; tekilleştirme kişi başınadır."""
    items = [
        texts.card_notice(notice)
        for notice in await reminders.card_notices(
            session, today=today, due_reminder_days=settings.due_reminder_days
        )
    ]
    items += [
        texts.period_summary(summary)
        for summary in await reminders.period_summaries(session, today=today)
    ]
    statuses = await budgets.monthly_status(session, year=today.year, month=today.month)
    items += [texts.budget_alert(alert) for alert in budgets.alerts_for(statuses)]
    usages = await cards.card_usage(session)
    items += [
        texts.card_limit_alert(alert)
        for alert in cards.alerts_for(usages, year=today.year, month=today.month)
    ]
    return items


async def run_daily_jobs(
    settings: Settings, session_factory, *, now: datetime | None = None
) -> int:
    """Günün işlerini yapar; oluşturulan bildirim sayısını döndürür.

    Sabit gider üretimi hatırlatma ayarından bağımsızdır: bildirimleri kapatmış
    bir kişi kirasının kaydedilmemesini istememiştir.
    """
    now = now or local_now(settings.timezone)
    if now.hour != settings.reminder_hour:
        return 0

    async with session_factory() as session:
        created = await recurring.generate_due(session, today=now.date())

        if not settings.enable_reminders:
            return 0
        recipients = await _recipients(session)
        if not recipients:
            return 0

        items = [
            texts.recurring_created(
                name=item.template_name,
                amount_minor=item.expense.total_amount_minor,
                when=item.expense.transaction_date,
                public_id=item.expense.public_id,
            )
            for item in created
        ]
        items += await pending_messages(session, settings, today=now.date())
        return await notifications.notify(
            session, settings, users=recipients, items=items
        )


async def run_scheduler(
    settings: Settings, session_factory, *, tick_seconds: int = TICK_SECONDS
) -> None:
    logger.info(
        "Hatırlatma zamanlayıcısı başladı (saat %02d:00, %s)",
        settings.reminder_hour,
        settings.timezone,
    )
    while True:
        try:
            count = await run_daily_jobs(settings, session_factory)
            if count:
                logger.info("%d bildirim oluşturuldu", count)
        except asyncio.CancelledError:
            logger.info("Hatırlatma zamanlayıcısı durduruldu")
            raise
        except Exception:
            # Zamanlayici tek bir hatali turda olmemelidir: bir sonraki
            # uyanista yeniden denemek, bildirimleri tamamen kaybetmekten iyidir.
            logger.exception("Hatırlatma döngüsünde beklenmedik hata")
        await asyncio.sleep(tick_seconds)


def start_scheduler_task(settings: Settings, session_factory) -> asyncio.Task:
    return asyncio.create_task(run_scheduler(settings, session_factory))
