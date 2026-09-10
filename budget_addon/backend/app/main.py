"""FastAPI uygulaması.

Uygulama iki farklı bağlamda çalışacak şekilde kurulur ve aradaki tek fark
`trust_ingress_headers` bayrağıdır:

- **Ingress örneği** (varsayılan port 8099): yalnızca Home Assistant
  Supervisor ağından erişilebilir, `X-Remote-User-Id` başlığına güvenir.
- **Genel örnek** (port 8100, KeenDNS üzerinden yayımlanır): başlığa
  **güvenmez**, yalnızca Telegram `initData` imzasını kabul eder.

Aynı kod, aynı iş kuralları; yalnızca kimliğin nereden geldiği değişir.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .admin_api import router as admin_router
from .api import router
from .auth_api import router as auth_router
from .notifications_api import router as notifications_router
from .receipts_api import router as receipts_router
from .services.scheduler import start_scheduler_task
from .security.setup import announce_setup_code, ensure_setup_code, setup_required
from .bot.runner import start_polling_task
from .ha_publisher import start_publisher_task
from .config import Settings, get_settings
from .database import dispose_engine, get_session_factory
from .services.seed import seed_all

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = (
    "İşlem tamamlanamadı. Verileriniz kaydedilmedi. Lütfen tekrar deneyin."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    logger.info("Uygulama başlıyor: %s", settings.safe_summary())
    async with get_session_factory()() as session:
        await seed_all(session, settings)
        if await setup_required(session):
            # Kod her acilista gunluge yeniden yazilir: kullanici eklentiyi
            # yeniden baslatarak kodu kolayca bulabilmelidir.
            announce_setup_code(ensure_setup_code(settings))

    bot_task = None
    publisher_task = None
    scheduler_task = None
    if settings.enable_bot:
        bot_task = start_polling_task(settings, get_session_factory())
        # Sensorler yalnizca tek surecten yazilir; iki uvicorn ornegi ayni
        # degerleri yazsaydi ikisi de dogru olurdu ama is bosuna iki katina
        # cikardi. Bot bayragi zaten "birincil surec" anlamini tasiyor.
        publisher_task = start_publisher_task(settings, get_session_factory())
        scheduler_task = start_scheduler_task(settings, get_session_factory())
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
        if publisher_task is not None:
            publisher_task.cancel()
            with suppress(asyncio.CancelledError):
                await publisher_task
        if bot_task is not None:
            # Polling sonsuz dongudur; kapanista acikca iptal edilip
            # bitmesi beklenmezse surec asili kalir.
            bot_task.cancel()
            with suppress(asyncio.CancelledError):
                await bot_task
        await dispose_engine()


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Derlenmiş arayüzü kök adresten sunar.

    Bağlama **API ve /health tanımlandıktan sonra** yapılır: kökten yapılan bir
    statik bağlama daha önce eklenirse `/api/...` isteklerini gölgeler ve
    arayüz çalışırken sunucu ölmüş gibi görünür.

    Arayüz derlenmemişse bağlama atlanır; bot ve API yine çalışır.
    """
    dist = Path(settings.frontend_dist) if settings.frontend_dist else FRONTEND_DIST
    if not (dist / "index.html").exists():
        logger.warning("Arayüz derlenmemiş (%s); yalnızca API sunuluyor", dist)
        return
    # html=True: bilinmeyen yollar index.html'e duser, SPA yonlendirmesi calisir.
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    logger.info("Arayüz sunuluyor: %s", dist)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Aile Bütçe Takip",
        version="1.0.0",
        lifespan=lifespan,
        # Uretimde API kesif arayuzleri kapalidir.
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    if settings.public_url:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            # Joker kullanilmaz: yalnizca yapilandirilmis adres kabul edilir.
            allow_origins=[settings.public_url.rstrip("/")],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(notifications_router)
    app.include_router(receipts_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    _mount_frontend(app, settings)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        """Beklenmeyen hatada kullanıcıya yığın izi gösterilmez.

        Gerçek hata sunucu logunda kalır; istemci yalnızca genel bir mesaj
        görür.
        """
        logger.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_MESSAGE})

    return app


app = create_app()
