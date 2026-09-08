"""Bot yetkilendirme filtresi.

Yetkisiz bir kullanıcı **hiçbir** finansal veri, buton veya menü görmemelidir.
Bu yüzden kontrol handler'ların içinde değil, hepsinin önünde bir middleware
olarak durur: yeni bir handler eklendiğinde kontrolü eklemeyi unutmak mümkün
olmaz.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject, User as TelegramUser
from sqlalchemy import select

from ..config import Settings
from ..models.user import User

logger = logging.getLogger(__name__)

UNAUTHORIZED_MESSAGE = "⛔ Bu botu kullanma yetkiniz bulunmuyor."


class AuthorizationMiddleware(BaseMiddleware):
    """Yetkisiz güncellemeleri handler'lara ulaşmadan durdurur.

    Yetkili kullanıcılar için veritabanındaki `User` kaydını `data["user"]`
    olarak geçirir; handler'lar kimliği yeniden çözmek zorunda kalmaz.
    """

    def __init__(self, settings: Settings, session_factory) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user: TelegramUser | None = data.get("event_from_user")
        if telegram_user is None:
            return None

        if telegram_user.id not in self._settings.authorized_ids:
            logger.warning(
                "Yetkisiz Telegram kullanıcısı engellendi: %s", telegram_user.id
            )
            await _refuse(event)
            return None

        async with self._session_factory() as session:
            user = await session.scalar(
                select(User).where(
                    User.telegram_user_id == telegram_user.id,
                    User.is_active.is_(True),
                )
            )
            if user is None:
                await _refuse(event)
                return None
            data["user"] = user
            data["session"] = session
            return await handler(event, data)


async def _refuse(event: TelegramObject) -> None:
    """Reddedilen kullanıcıya tek bir mesaj döner, başka hiçbir şey göstermez.

    Tip kontrolu yerine yetenek kontrolu yapilir: aiogram'in gelecekteki bir
    surumunde yeni bir olay turu eklendiginde, reddin sessizce kaybolmasi
    yerine ayni mesaj gonderilmeye devam eder.
    """
    if isinstance(event, CallbackQuery):
        # show_alert: butona basan kullanici da sessiz kalmamali.
        await event.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
        return
    answer = getattr(event, "answer", None)
    if answer is not None:
        await answer(UNAUTHORIZED_MESSAGE)
        return
    logger.error("Yetkisiz erişim reddedildi ama yanıt gönderilemedi: %r", type(event))
