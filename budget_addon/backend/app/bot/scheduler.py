"""Hatırlatmaların zamanlanması ve gönderilmesi.

Ayrı bir zamanlayıcı kütüphanesi kullanılmaz: tek bir asenkron döngü dakikada
bir uyanır, yerel saat hatırlatma saatine geldiyse günün hatırlatmalarını
gönderir. Bu, eklentiye yeni bir bağımlılık eklemeden ve saat diliminin
tamamen `settings.timezone` üzerinden yönetilmesini bozmadan işi görür.

Tekrarlı bildirim riski döngüyle değil **veritabanıyla** engellenir: gönderilen
her hatırlatma `notification_log` tablosuna yazılır. Eklenti gün içinde on kez
yeniden başlasa da aynı hatırlatma ikinci kez gönderilmez.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import NotificationLog, User
from ..services import reminders
from ..utils.time import local_now
from . import messages

logger = logging.getLogger(__name__)

TICK_SECONDS = 60


async def _already_sent(session: AsyncSession, *, kind: str, reference: str) -> bool:
    return (
        await session.scalar(
            select(NotificationLog.id).where(
                NotificationLog.kind == kind,
                NotificationLog.reference == reference,
            )
        )
    ) is not None


async def _mark_sent(session: AsyncSession, *, kind: str, reference: str) -> None:
    session.add(NotificationLog(kind=kind, reference=reference))
    try:
        await session.commit()
    except IntegrityError:
        # Iki surec ayni anda ayni hatirlatmayi isaretlemeye calisirsa benzersizlik
        # kisiti devreye girer; bu bir hata degil, tam olarak istenen sonuctur.
        await session.rollback()


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


async def pending_reminders(
    session: AsyncSession, settings: Settings, *, today
) -> list[tuple[str, str, str]]:
    """Bugün gönderilecek hatırlatmaları `(tür, anahtar, metin)` olarak verir.

    Kullanıcıdan bağımsızdır: aynı içerik hatırlatması açık olan herkese
    gider, tekilleştirme kullanıcı bazında yapılır.
    """
    items: list[tuple[str, str, str]] = []
    for notice in await reminders.card_notices(
        session, today=today, due_reminder_days=settings.due_reminder_days
    ):
        items.append((notice.kind, notice.key, messages.card_notice(notice)))
    for summary in await reminders.period_summaries(session, today=today):
        items.append((summary.kind, summary.key, messages.period_summary(summary)))
    return items


async def deliver_due_reminders(
    bot, settings: Settings, session_factory, *, now: datetime | None = None
) -> int:
    """Saati geldiyse hatırlatmaları gönderir ve gönderilen sayısını döner.

    Saat kontrolü burada yapılır ki döngü basit kalsın; dakikalık uyanışların
    tamamı bu fonksiyona uğrar ve yalnızca hatırlatma saatinde iş yapar.
    """
    now = now or local_now(settings.timezone)
    if now.hour != settings.reminder_hour:
        return 0

    sent = 0
    async with session_factory() as session:
        recipients = await _recipients(session)
        if not recipients:
            return 0

        items = await pending_reminders(session, settings, today=now.date())
        for kind, key, text in items:
            for user in recipients:
                reference = f"{user.id}:{key}"
                if await _already_sent(session, kind=kind, reference=reference):
                    continue
                if await _send(bot, user.telegram_user_id, text):
                    await _mark_sent(session, kind=kind, reference=reference)
                    sent += 1
    return sent


async def _send(bot, chat_id: int, text: str) -> bool:
    """Mesajı gönderir. Başarısızsa `False` döner ve hatırlatma işaretlenmez.

    Geçici bir ağ hatası hatırlatmayı yutmamalıdır: işaretlenmediği için bir
    sonraki uyanışta yeniden denenir. Kullanıcı botu engellemişse yeniden
    denemenin anlamı yoktur; o durum çağıran tarafta değil burada, gönderilmiş
    sayılarak kapatılır.
    """
    from aiogram.exceptions import TelegramForbiddenError

    try:
        await bot.send_message(chat_id, text)
        return True
    except TelegramForbiddenError:
        logger.warning(
            "Kullanıcı %s botu engellemiş; hatırlatma gönderilemedi", chat_id
        )
        return True
    except Exception:
        logger.exception("Hatırlatma gönderilemedi (chat_id=%s)", chat_id)
        return False


async def run_scheduler(
    bot, settings: Settings, session_factory, *, tick_seconds: int = TICK_SECONDS
) -> None:
    """Hatırlatma döngüsü. Bot görevinin ömrü boyunca çalışır."""
    logger.info(
        "Hatırlatma zamanlayıcısı başladı (saat %02d:00, %s)",
        settings.reminder_hour,
        settings.timezone,
    )
    while True:
        try:
            count = await deliver_due_reminders(bot, settings, session_factory)
            if count:
                logger.info("%d hatırlatma gönderildi", count)
        except asyncio.CancelledError:
            logger.info("Hatırlatma zamanlayıcısı durduruldu")
            raise
        except Exception:
            # Zamanlayici, tek bir hatali dongude olmemelidir: bir sonraki
            # uyanista yeniden denemek, bildirimleri tamamen kaybetmekten iyidir.
            logger.exception("Hatırlatma döngüsünde beklenmedik hata")
        await asyncio.sleep(tick_seconds)
