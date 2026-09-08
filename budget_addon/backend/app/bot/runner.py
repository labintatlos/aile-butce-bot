"""Bot yaşam döngüsü.

Güncellemeler **long polling** ile alınır: webhook, dışarıdan erişilebilir bir
HTTPS adresi gerektirirdi ve sistemin en kırılgan bağımlılığı olurdu.

Polling görevi FastAPI'nin lifespan bağlamında başlatılır ve kapanışta düzgün
durdurulur.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from ..config import Settings
from .authorization import AuthorizationMiddleware
from .handlers import router

logger = logging.getLogger(__name__)


def build_dispatcher(settings: Settings, session_factory) -> Dispatcher:
    dispatcher = Dispatcher()
    guard = AuthorizationMiddleware(settings, session_factory)
    # Hem mesajlar hem buton tiklamalari ayni kontrolden gecer.
    dispatcher.message.middleware(guard)
    dispatcher.callback_query.middleware(guard)
    dispatcher.include_router(router)
    dispatcher["settings"] = settings
    return dispatcher


def build_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_polling(settings: Settings, session_factory) -> None:
    bot = build_bot(settings)
    dispatcher = build_dispatcher(settings, session_factory)
    try:
        # Birikmis guncellemeler atlanir: yeniden baslatmada eski mesajlara
        # toplu yanit vermek kafa karistirici olurdu.
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        logger.info("Bot polling durduruldu")
        raise
    finally:
        await bot.session.close()


def start_polling_task(settings: Settings, session_factory) -> asyncio.Task | None:
    """Polling görevini başlatır. Token yoksa bot sessizce devre dışı kalır."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token yapılandırılmamış; bot başlatılmadı")
        return None
    return asyncio.create_task(run_polling(settings, session_factory))
