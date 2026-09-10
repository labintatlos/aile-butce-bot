"""Kimlik çözümleme: dört kaynak, tek çıkış.

Arayüz dört bağlamda çalışır ve her birinde kimlik farklı yerden gelir:

1. **Home Assistant Ingress** — HA kullanıcıyı kendi oturumuyla doğrular ve
   `X-Remote-User-Id` başlığını ekler.
2. **Telegram Mini App** — `Authorization: tma <initData>` başlığı, bot
   token'ıyla imzalanmış.
3. **Yerel geliştirme** — `X-Dev-Telegram-User-Id`, yalnızca açıkça
   etkinleştirildiğinde.
4. **Web sitesi** — kullanıcı adı ve şifreyle girişte verilen imzalı oturum
   çerezi (bkz. `sessions.py`).

Hangi kaynaktan gelirse gelsin sonuç aynıdır: veritabanındaki aktif bir `User`.
Böylece iş kuralları kimliğin nereden geldiğini bilmek zorunda kalmaz.

**Güvenlik notu:** `X-Remote-User-Id` başlığına yalnızca `trust_ingress_headers`
açıkken güvenilir. Bu bayrak, uygulamanın yalnızca Supervisor'ın Ingress ağından
erişilebildiği örnek için açılır. İnternete açık portu dinleyen örnekte kapalıdır,
çünkü orada başlığı isteyen herkes uydurabilir.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_session
from ..models.user import User
from .accounts import has_login
from .sessions import COOKIE_NAME, SessionClaims, password_fingerprint, read_token, resolve_secret
from .telegram_auth import TelegramAuthError, validate_init_data

logger = logging.getLogger(__name__)

TELEGRAM_SCHEME = "tma "
INGRESS_USER_HEADER = "X-Remote-User-Id"
DEV_USER_HEADER = "X-Dev-Telegram-User-Id"

SOURCE_SESSION = "session"

UNAUTHORIZED_MESSAGE = "Kimlik doğrulama gerekli"
FORBIDDEN_MESSAGE = "Bu uygulamayı kullanma yetkiniz yok"


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    """Doğrulanmış kimlik. `source` loglama ve arayüzün çıkış düğmesi içindir."""

    source: str
    telegram_user_id: int | None = None
    ha_user_id: str | None = None
    session: SessionClaims | None = None


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


def _from_session_cookie(
    request: Request, settings: Settings
) -> ResolvedIdentity | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    claims = read_token(resolve_secret(settings), token)
    if claims is None:
        return None
    return ResolvedIdentity(source=SOURCE_SESSION, session=claims)


def resolve_identity(request: Request, settings: Settings) -> ResolvedIdentity:
    """Kaynakları sırayla dener, ilk geçerli olanı döndürür."""
    try:
        for resolver in (
            _from_ingress,
            _from_telegram,
            _from_dev_header,
            _from_session_cookie,
        ):
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


def can_use_web_login(user: User) -> bool:
    return user.is_active and has_login(user)


async def _lookup_user(
    session: AsyncSession, identity: ResolvedIdentity, settings: Settings
) -> User | None:
    if identity.session is not None:
        user = await session.get(User, identity.session.user_id)
        if user is None or not can_use_web_login(user):
            return None
        # Sifre degistiyse parmak izi tutmaz ve eski cerez gecersiz olur.
        if not hmac.compare_digest(
            password_fingerprint(user.password_hash), identity.session.fingerprint
        ):
            return None
        return user

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
        if identity.source == SOURCE_SESSION:
            # Gecersizlesmis oturum "yetkisiz" degil "yeniden giris gerekli"dir;
            # arayuz 401 gorunce giris ekranina doner.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_MESSAGE
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_MESSAGE
        )
    request.state.auth_source = identity.source
    return user
