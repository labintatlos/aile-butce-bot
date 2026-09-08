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

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
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
    try:
        yield
    finally:
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

    if settings.webapp_public_url:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            # Joker kullanilmaz: yalnizca yapilandirilmis adres kabul edilir.
            allow_origins=[settings.webapp_public_url.rstrip("/")],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(router)

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
