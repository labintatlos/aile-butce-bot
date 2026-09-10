"""Bildirimler: site içi liste, kişinin bildirim tercihleri ve cihaz abonelikleri."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models import Notification, PushSubscription, User
from .security.identity import current_user
from .services import email_delivery, notifications, webpush
from .services.notification_texts import KIND_TEST, LINK_NOTIFICATIONS

router = APIRouter(prefix="/api")

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
UNPROCESSABLE = 422


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    is_read: bool


class NotificationListOut(BaseModel):
    unread: int
    items: list[NotificationOut]


class MarkReadIn(BaseModel):
    ids: list[int] | None = None


class UnreadOut(BaseModel):
    unread: int


class NotificationSettingsOut(BaseModel):
    reminders_enabled: bool
    reminder_hour: int
    email: str | None
    email_notifications: bool
    email_available: bool
    push_public_key: str
    push_devices: int


class NotificationSettingsIn(BaseModel):
    reminders_enabled: bool | None = None
    email: str | None = Field(default=None, max_length=254)
    email_notifications: bool | None = None


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=64)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1024)
    keys: PushKeysIn


class PushEndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1024)


class TestNotificationOut(BaseModel):
    email: str
    push_sent: int
    push_devices: int


def _out(note: Notification) -> NotificationOut:
    return NotificationOut(
        id=note.id,
        kind=note.kind,
        title=note.title,
        body=note.body,
        link=note.link,
        created_at=note.created_at,
        is_read=note.read_at is not None,
    )


@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    limit: int = Query(30, ge=0, le=100),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationListOut:
    """`limit=0` yalnızca okunmamış sayısını döndürür; menüdeki rozet içindir."""
    items = await notifications.recent(session, user, limit=limit) if limit else []
    return NotificationListOut(
        unread=await notifications.unread_count(session, user),
        items=[_out(note) for note in items],
    )


@router.post("/notifications/read", response_model=UnreadOut)
async def mark_notifications_read(
    payload: MarkReadIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> UnreadOut:
    await notifications.mark_read(session, user, payload.ids)
    return UnreadOut(unread=await notifications.unread_count(session, user))


async def _settings_out(
    session: AsyncSession, settings: Settings, user: User
) -> NotificationSettingsOut:
    devices = await session.scalars(
        select(PushSubscription.id).where(PushSubscription.user_id == user.id)
    )
    return NotificationSettingsOut(
        reminders_enabled=user.reminders_enabled,
        reminder_hour=settings.reminder_hour,
        email=user.email,
        email_notifications=user.email_notifications,
        email_available=email_delivery.email_configured(settings),
        push_public_key=webpush.public_key_for_browser(settings),
        push_devices=len(devices.all()),
    )


@router.get("/notifications/settings", response_model=NotificationSettingsOut)
async def read_notification_settings(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> NotificationSettingsOut:
    return await _settings_out(session, settings, user)


@router.patch("/notifications/settings", response_model=NotificationSettingsOut)
async def update_notification_settings(
    payload: NotificationSettingsIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> NotificationSettingsOut:
    if payload.email is not None:
        email = payload.email.strip()
        if email and not EMAIL_PATTERN.fullmatch(email):
            raise HTTPException(UNPROCESSABLE, "E-posta adresi geçersiz.")
        user.email = email or None
        if not email:
            user.email_notifications = False
    if payload.email_notifications is not None:
        if payload.email_notifications and not user.email:
            raise HTTPException(UNPROCESSABLE, "Önce bir e-posta adresi girin.")
        user.email_notifications = payload.email_notifications
    if payload.reminders_enabled is not None:
        user.reminders_enabled = payload.reminders_enabled
    await session.commit()
    return await _settings_out(session, settings, user)


@router.post("/push/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe_push(
    payload: PushSubscriptionIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        endpoint = webpush.validate_endpoint(payload.endpoint)
    except ValueError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    subscription = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    if subscription is None:
        subscription = PushSubscription(endpoint=endpoint)
        session.add(subscription)
    subscription.user_id = user.id
    subscription.p256dh = payload.keys.p256dh
    subscription.auth = payload.keys.auth
    await session.commit()


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_push(
    payload: PushEndpointIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == user.id,
        )
    )
    await session.commit()


@router.post("/notifications/test", response_model=TestNotificationOut)
async def send_test_notification(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TestNotificationOut:
    """Kişinin açtığı bütün kanallara bir deneme bildirimi gönderir."""
    note = Notification(
        user_id=user.id,
        kind=KIND_TEST,
        title="Deneme bildirimi",
        body="Bildirimler çalışıyor. Hatırlatmalar bu şekilde gelecek.",
        link=LINK_NOTIFICATIONS,
    )
    session.add(note)
    await session.commit()
    report = await notifications.deliver(session, settings, user, note)
    return TestNotificationOut(
        email=report.email, push_sent=report.push_sent, push_devices=report.push_devices
    )
