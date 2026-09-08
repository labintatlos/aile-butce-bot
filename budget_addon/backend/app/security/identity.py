"""Kimlik çözümleme: üç kaynak, tek çıkış.

Arayüz üç bağlamda çalışır ve her birinde kimlik farklı yerden gelir:

1. **Home Assistant Ingress** — HA kullanıcıyı kendi oturumuyla doğrular ve
   `X-Remote-User-Id` başlığını ekler.
2. **Telegram Mini App** — `Authorization: tma <initData>` başlığı, bot
   token'ıyla imzalanmış.
3. **Yerel geliştirme** — `X-Dev-Telegram-User-Id`, yalnızca açıkça
   etkinleştirildiğinde.

Hangi kaynaktan gelirse gelsin sonuç aynıdır: veritabanındaki aktif bir `User`.
Böylece iş kuralları kimliğin nereden geldiğini bilmek zorunda kalmaz.

**Güvenlik notu:** `X-Remote-User-Id` başlığına yalnızca `trust_ingress_headers`
açıkken güvenilir. Bu bayrak, uygulamanın yalnızca Supervisor'ın Ingress ağından
erişilebildiği örnek için açılır. İnternete açık portu dinleyen örnekte kapalıdır,
çünkü orada başlığı isteyen herkes uydurabilir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_session
from ..models.user import User
from .telegram_auth import TelegramAuthError, validate_init_data

logger = logging.getLogger(__name__)

TELEGRAM_SCHEME = "tma "
INGRESS_USER_HEADER = "X-Remote-User-Id"
DEV_USER_HEADER = "X-Dev-Telegram-User-Id"

UNAUTHORIZED_MESSAGE = "Kimlik doğrulama gerekli"
FORBIDDEN_MESSAGE = "Bu uygulamayı kullanma yetkiniz yok"


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    """Doğrulanmış kimlik. `source` yalnızca loglama ve teşhis içindir."""

    source: str
    telegram_user_id: int | None = None
    ha_user_id: str | None = None


def _from_ingress(request: Request, settings: Settings) -> ResolvedIdentity | None:
    if not settings.trust_ingress_headers:
        return None
    ha_user_id = request.headers.get(INGRESS_USER_HEADER)
    if not ha_user_id:
        return None
    return ResolvedIdentity(source="ingress", ha_user_id=ha_user_id)


def _from_telegram(request: Request, settings: Settings) -> ResolvedIdentity | None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith(TELEGRAM_SCHEME):
        return None
    identity = validate_init_data(
        authorization[len(TELEGRAM_SCHEME) :],
        settings.telegram_bot_token,
        settings.telegram_auth_max_age_seconds,
    )
    return ResolvedIdentity(
        source="telegram", telegram_user_id=identity.telegram_user_id
    )


def _from_dev_header(request: Request, settings: Settings) -> ResolvedIdentity | None:
    if not settings.allow_dev_auth:
        return None
    raw = request.headers.get(DEV_USER_HEADER)
    if not raw:
        return None
    try:
        return ResolvedIdentity(source="dev", telegram_user_id=int(raw))
    except ValueError:
        return None


def resolve_identity(request: Request, settings: Settings) -> ResolvedIdentity:
    """Üç kaynağı sırayla dener, ilk geçerli olanı döndürür."""
    try:
        for resolver in (_from_ingress, _from_telegram, _from_dev_header):
            identity = resolver(request, settings)
            if identity is not None:
                return identity
    except TelegramAuthError as exc:
        # Hatanin kendisi guvenlidir; initData icerigi asla loglanmaz.
        logger.warning("Telegram doğrulaması başarısız: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_MESSAGE
    )


async def _lookup_user(
    session: AsyncSession, identity: ResolvedIdentity, settings: Settings
) -> User | None:
    if identity.ha_user_id is not None:
        telegram_id = settings.ha_user_mapping.get(identity.ha_user_id)
        if telegram_id is None:
            # Eslemesi olmayan bir HA kullanicisi varsayilan kisiye baglanmaz:
            # harcamayi kimin girdigi belirsizlesir ve kisi bazli rapor bozulur.
            logger.warning(
                "Eşlenmemiş Home Assistant kullanıcısı erişmeye çalıştı: %s",
                identity.ha_user_id,
            )
            return None
        return await session.scalar(
            select(User).where(
                User.telegram_user_id == telegram_id, User.is_active.is_(True)
            )
        )

    if identity.telegram_user_id not in settings.authorized_ids:
        return None
    return await session.scalar(
        select(User).where(
            User.telegram_user_id == identity.telegram_user_id,
            User.is_active.is_(True),
        )
    )


async def current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI bağımlılığı: doğrulanmış ve yetkili kullanıcıyı döndürür."""
    identity = resolve_identity(request, settings)
    user = await _lookup_user(session, identity, settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_MESSAGE
        )
    return user
