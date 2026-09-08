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
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.utils.token import TokenValidationError

from ..config import Settings
from .authorization import AuthorizationMiddleware
from .handlers import router
from .settings_commands import router as settings_router

logger = logging.getLogger(__name__)


def build_dispatcher(settings: Settings, session_factory) -> Dispatcher:
    dispatcher = Dispatcher()
    guard = AuthorizationMiddleware(settings, session_factory)
    # Hem mesajlar hem buton tiklamalari ayni kontrolden gecer.
    dispatcher.message.middleware(guard)
    dispatcher.callback_query.middleware(guard)
    # Ayar komutlari once eklenir: handlers icindeki serbest metin yakalayicisi
    # aksi halde /kartekle gibi komutlari hizli giris sanip yutardi.
    dispatcher.include_router(settings_router)
    dispatcher.include_router(router)
    dispatcher["settings"] = settings
    return dispatcher


def build_bot(settings: Settings) -> Bot:
    """Bot nesnesini kurar.

    Token bicimsel olarak gecersizse aiogram burada hata verir; cagiran taraf
    bunu yakalayip anlasilir bir mesaja cevirir.
    """
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_polling(settings: Settings, session_factory) -> None:
    """Telegram güncellemelerini dinler.

    Bot bir arka plan görevidir ve **web sunucusunu düşürmez**: Home Assistant
    paneli, token yanlış olsa bile çalışmaya devam etmelidir. Ancak hata
    sessizce yutulmaz; aksi halde kullanıcı token'ını yanlış girdiğini hiçbir
    yerden anlayamazdı.
    """
    # Bot nesnesi de try icinde kurulur: bicimsel olarak bozuk bir token
    # hatasi burada olusur ve disarida kalsaydi yakalanamazdi.
    bot: Bot | None = None
    try:
        bot = build_bot(settings)
        dispatcher = build_dispatcher(settings, session_factory)
        # Birikmis guncellemeler atlanir: yeniden baslatmada eski mesajlara
        # toplu yanit vermek kafa karistirici olurdu.
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Telegram botu dinlemeye başladı")
        await dispatcher.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        logger.info("Bot polling durduruldu")
        raise
    except (TelegramUnauthorizedError, TokenValidationError):
        logger.error(
            "Telegram bot token geçersiz; bot devre dışı. Eklenti ayarlarından "
            "'telegram_bot_token' alanını BotFather'dan aldığınız değerle "
            "güncelleyin. Arayüz Home Assistant panelinden çalışmaya devam ediyor."
        )
    except Exception:
        logger.exception(
            "Telegram botu beklenmedik bir hatayla durdu; arayüz çalışmaya "
            "devam ediyor."
        )
    finally:
        if bot is not None:
            await bot.session.close()


def start_polling_task(settings: Settings, session_factory) -> asyncio.Task | None:
    """Polling görevini başlatır. Token yoksa bot sessizce devre dışı kalır."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token yapılandırılmamış; bot başlatılmadı")
        return None
    return asyncio.create_task(run_polling(settings, session_factory))
