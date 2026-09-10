"""Web sitesi girişi ve oturum sahibinin kendi hesabı.

Kişiler ve şifreler sitedeki yönetici ekranından yönetilir (bkz.
`admin_api.py`); herkese açık bir kayıt formu yoktur. Aile uygulamasında kayıt
formu yalnızca saldırı yüzeyi eklerdi.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.user import User
from .schemas import UserOut
from .security.accounts import AccountError, check_password, has_login
from .security.identity import SOURCE_SESSION, can_use_web_login, current_user
from .security.passwords import burn_verification_time, hash_password, verify_password
from .security.sessions import (
    COOKIE_NAME,
    REMEMBER_SECONDS,
    SHORT_SECONDS,
    issue_token,
    resolve_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW_SECONDS = 15 * 60

INVALID_CREDENTIALS_MESSAGE = "Kullanıcı adı veya şifre hatalı"
TOO_MANY_ATTEMPTS_MESSAGE = (
    "Çok fazla hatalı deneme yapıldı. Lütfen 15 dakika sonra tekrar deneyin."
)
WRONG_CURRENT_PASSWORD_MESSAGE = "Mevcut şifre hatalı"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember: bool = True


class MeOut(BaseModel):
    id: int
    display_name: str
    role: str
    username: str | None
    is_admin: bool
    reminders_enabled: bool
    auth_source: str


class MeUpdateIn(BaseModel):
    reminders_enabled: bool | None = None


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class LoginThrottle:
    """Adres başına hatalı giriş sayacı.

    Yalnızca **hatalı** denemeleri sayar; doğru şifreyle giren kullanıcı hiçbir
    zaman yavaşlatılmaz. Sayaç kullanıcı adına göre değil adrese göre tutulur:
    kullanıcı adına göre tutulsaydı, adı bilen biri gerçek sahibini kilitleyebilirdi.
    """

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and now - attempts[0] > FAILED_LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        return attempts

    def is_blocked(self, key: str, now: float) -> bool:
        return len(self._recent(key, now)) >= MAX_FAILED_LOGINS

    def record_failure(self, key: str, now: float) -> None:
        self._recent(key, now).append(now)

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)


def login_throttle(app: FastAPI) -> LoginThrottle:
    throttle = getattr(app.state, "login_throttle", None)
    if throttle is None:
        throttle = app.state.login_throttle = LoginThrottle()
    return throttle


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _is_https(request: Request) -> bool:
    forwarded = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    return request.url.scheme == "https" or forwarded == "https"


def set_session_cookie(
    response: Response,
    request: Request,
    settings: Settings,
    user: User,
    *,
    remember: bool = True,
) -> None:
    lifetime = REMEMBER_SECONDS if remember else SHORT_SECONDS
    token = issue_token(
        resolve_secret(settings),
        user_id=user.id,
        password_hash=user.password_hash or "",
        lifetime_seconds=lifetime,
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        # "Beni hatirla" kapaliysa cerez tarayici kapaninca silinir; belirtecin
        # kendi suresi yine de kisa tutulur.
        max_age=lifetime if remember else None,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )


def me_out(user: User, source: str) -> MeOut:
    return MeOut(
        id=user.id,
        display_name=user.display_name,
        role=user.role,
        username=user.username,
        is_admin=user.is_admin,
        reminders_enabled=user.reminders_enabled,
        auth_source=source,
    )


@router.post("/auth/login", response_model=MeOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MeOut:
    throttle = login_throttle(request.app)
    key = client_key(request)
    now = time.monotonic()
    if throttle.is_blocked(key, now):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS_MESSAGE)

    username = payload.username.strip().lower()
    user = await session.scalar(select(User).where(User.username == username))
    if user is None:
        burn_verification_time(payload.password)
        valid = False
    else:
        valid = verify_password(payload.password, user.password_hash) and can_use_web_login(user)

    if not valid or user is None:
        throttle.record_failure(key, now)
        # Kullanici adi loglanmaz: sifre yanlislikla o alana yazilmis olabilir.
        logger.warning("Başarısız web girişi denemesi: %s", key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS_MESSAGE)

    throttle.clear(key)
    set_session_cookie(response, request, settings, user, remember=payload.remember)
    logger.info("Web girişi: %s", user.display_name)
    return me_out(user, SOURCE_SESSION)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me", response_model=MeOut)
async def read_me(request: Request, user: User = Depends(current_user)) -> MeOut:
    return me_out(user, request.state.auth_source)


@router.patch("/me", response_model=MeOut)
async def update_me(
    payload: MeUpdateIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    if payload.reminders_enabled is not None:
        user.reminders_enabled = payload.reminders_enabled
        await session.commit()
    return me_out(user, request.state.auth_source)


@router.post("/me/password", response_model=MeOut)
async def change_own_password(
    payload: PasswordChangeIn,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MeOut:
    """Kişi kendi şifresini değiştirir.

    Diğer cihazlardaki oturumlar kendiliğinden kapanır; bu cihazdaki oturum
    yeni şifreyle verilen çerezle sürer.
    """
    if not has_login(user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu hesabın web girişi yok")

    throttle = login_throttle(request.app)
    key = client_key(request)
    now = time.monotonic()
    if throttle.is_blocked(key, now):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS_MESSAGE)
    if not verify_password(payload.current_password, user.password_hash):
        throttle.record_failure(key, now)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, WRONG_CURRENT_PASSWORD_MESSAGE)

    try:
        new_password = check_password(payload.new_password)
    except AccountError as exc:
        raise HTTPException(422, str(exc)) from exc

    throttle.clear(key)
    user.password_hash = hash_password(new_password)
    await session.commit()
    if request.state.auth_source == SOURCE_SESSION:
        set_session_cookie(response, request, settings, user)
    logger.info("Şifre değiştirildi: %s", user.display_name)
    return me_out(user, request.state.auth_source)


@router.get("/users", response_model=list[UserOut])
async def read_users(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[UserOut]:
    """Filtreler ve kart sahibi seçimi için aktif kişiler."""
    users = (
        await session.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.id)
        )
    ).all()
    return [UserOut.model_validate(user) for user in users]
