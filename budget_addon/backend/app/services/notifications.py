"""Bildirimlerin oluşturulması, listelenmesi ve iletilmesi.

Her bildirim önce site içinde saklanır. Kişi açtıysa e-posta ve telefondaki
anlık bildirim de gönderilir; bu kanallar yardımcıdır: e-posta sunucusu veya
bildirim servisi o an yanıt vermese de bildirim sitede kaybolmaz.

Tekrarlı bildirim `notification_log` ile engellenir: aynı hatırlatma aynı
kişiye bir kez oluşturulur, eklenti gün içinde yeniden başlasa da.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import Notification, NotificationLog, PushSubscription, User
from ..models.base import utc_now
from . import email_delivery, webpush
from .notification_texts import LINK_NOTIFICATIONS, NotificationText

logger = logging.getLogger(__name__)

EMAIL_SENT = "sent"
EMAIL_SKIPPED = "skipped"
EMAIL_FAILED = "failed"
PUSH_ACCEPTED = frozenset({200, 201, 202})


@dataclass(slots=True)
class DeliveryReport:
    email: str = EMAIL_SKIPPED
    push_sent: int = 0
    push_devices: int = 0


async def notify(
    session: AsyncSession,
    settings: Settings,
    *,
    users: Iterable[User],
    items: Iterable[NotificationText],
) -> int:
    """Bildirimleri kişilere oluşturur ve iletir; oluşturulan sayıyı döndürür."""
    users = list(users)
    created: list[tuple[User, Notification]] = []
    for item in items:
        for user in users:
            reference = f"{user.id}:{item.key}"
            already = await session.scalar(
                select(NotificationLog.id).where(
                    NotificationLog.kind == item.kind,
                    NotificationLog.reference == reference,
                )
            )
            if already is not None:
                continue
            note = Notification(
                user_id=user.id,
                kind=item.kind,
                title=item.title,
                body=item.body,
                link=item.link,
            )
            session.add_all([note, NotificationLog(kind=item.kind, reference=reference)])
            try:
                await session.commit()
            except IntegrityError:
                # Iki surec ayni bildirimi ayni anda olusturmaya calisirsa
                # benzersizlik kisiti birini durdurur; istenen tam olarak budur.
                await session.rollback()
                continue
            created.append((user, note))

    for user, note in created:
        await deliver(session, settings, user, note)
    return len(created)


def site_link(settings: Settings, link: str | None) -> str | None:
    if not settings.public_url:
        return None
    return f"{settings.public_url.rstrip('/')}/#/{link or LINK_NOTIFICATIONS}"


async def deliver(
    session: AsyncSession, settings: Settings, user: User, note: Notification
) -> DeliveryReport:
    """Saklanmış bildirimi kişinin açtığı dış kanallara gönderir."""
    report = DeliveryReport()

    if user.email_notifications and user.email and email_delivery.email_configured(settings):
        url = site_link(settings, note.link)
        body = f"{note.body}\n\n{url}" if url else note.body
        try:
            await asyncio.to_thread(
                email_delivery.send_email, settings, to=user.email, subject=note.title, body=body
            )
            report.email = EMAIL_SENT
        except Exception:
            logger.exception("E-posta gönderilemedi (kişi %s)", user.id)
            report.email = EMAIL_FAILED

    subscriptions = list(
        (
            await session.scalars(
                select(PushSubscription).where(PushSubscription.user_id == user.id)
            )
        ).all()
    )
    report.push_devices = len(subscriptions)
    if not subscriptions:
        return report

    key = webpush.load_vapid_key(settings)
    subject = webpush.vapid_subject(settings)
    payload = {
        "title": note.title,
        "body": note.body,
        "url": f"#/{note.link or LINK_NOTIFICATIONS}",
        "tag": f"butce-{note.id}",
    }
    gone: list[PushSubscription] = []
    for subscription in subscriptions:
        try:
            status = await asyncio.to_thread(
                webpush.send_push,
                endpoint=subscription.endpoint,
                p256dh=subscription.p256dh,
                auth=subscription.auth,
                payload=payload,
                key=key,
                subject=subject,
            )
        except Exception:
            logger.exception("Anlık bildirim gönderilemedi (kişi %s)", user.id)
            continue
        if status in PUSH_ACCEPTED:
            report.push_sent += 1
        elif status in webpush.GONE_STATUSES:
            gone.append(subscription)
        else:
            logger.warning("Anlık bildirim servisi isteği reddetti (HTTP %s)", status)

    if gone:
        for subscription in gone:
            await session.delete(subscription)
        await session.commit()
        report.push_devices -= len(gone)
    return report


async def unread_count(session: AsyncSession, user: User) -> int:
    return await session.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    )


async def recent(session: AsyncSession, user: User, *, limit: int) -> list[Notification]:
    return list(
        (
            await session.scalars(
                select(Notification)
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            )
        ).all()
    )


async def mark_read(
    session: AsyncSession, user: User, ids: list[int] | None = None
) -> None:
    statement = (
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utc_now())
    )
    if ids is not None:
        statement = statement.where(Notification.id.in_(ids))
    await session.execute(statement)
    await session.commit()
