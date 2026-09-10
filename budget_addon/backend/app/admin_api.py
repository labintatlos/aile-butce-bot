"""Kişi yönetimi ve ilk yönetici kurulumu.

Kişiler ve şifreler eklenti ayarlarından değil, bu uç noktalardan yönetilir.
Kişi silinmez, devre dışı bırakılır: geçmiş harcamalar kimin girdiğini
göstermeye devam etmelidir.

İki koruma yöneticinin kendini kilitlemesini engeller: kimse kendi hesabını
kapatamaz veya kendi yönetici yetkisini kaldıramaz, ve her değişiklikten sonra
giriş yapabilen en az bir etkin yönetici kalmalıdır.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth_api import (
    TOO_MANY_ATTEMPTS_MESSAGE,
    MeOut,
    client_key,
    login_throttle,
    me_out,
    set_session_cookie,
)
from .config import Settings, get_settings
from .database import get_session
from .models.user import ROLE_OWNER, User
from .security.accounts import (
    AccountError,
    check_password,
    clean_display_name,
    clean_username,
    ensure_username_free,
    has_login,
)
from .security.identity import SOURCE_SESSION, current_user
from .security.passwords import hash_password
from .security.setup import (
    check_setup_code,
    clear_setup_code,
    ensure_setup_code,
    setup_required,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

ADMIN_REQUIRED_MESSAGE = "Bu işlem için yönetici yetkisi gerekli"
INVALID_SETUP_CODE_MESSAGE = (
    "Kurulum kodu hatalı. Kodu Home Assistant'ta eklentinin Günlük sekmesinde bulabilirsiniz."
)
SETUP_DONE_MESSAGE = "Kurulum zaten tamamlanmış. Giriş ekranını kullanın."
SELF_LOCKOUT_MESSAGE = (
    "Kendi hesabınızı kapatamaz veya kendi yönetici yetkinizi kaldıramazsınız. "
    "Bunu başka bir yönetici yapabilir."
)
LAST_ADMIN_MESSAGE = "Giriş yapabilen en az bir etkin yönetici kalmalıdır."

UNPROCESSABLE = 422
"""Starlette sabitin adini degistirdi; eski ad uyari veriyor, yenisi eski
surumlerde yok. Sayi her ikisinde de aynidir."""


def _invalid(exc: AccountError) -> HTTPException:
    return HTTPException(UNPROCESSABLE, str(exc))


# ---------------------------------------------------------------------------
# Ilk kurulum
# ---------------------------------------------------------------------------


class SetupStatusOut(BaseModel):
    required: bool


class SetupCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class SetupPersonOut(BaseModel):
    id: int
    display_name: str


class SetupIn(SetupCodeIn):
    user_id: int | None = None
    """Mevcut bir kişiyi sahiplenmek için; boşsa yeni kişi oluşturulur."""
    display_name: str | None = Field(default=None, max_length=64)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


async def _require_setup(session: AsyncSession) -> None:
    if not await setup_required(session):
        raise HTTPException(status.HTTP_409_CONFLICT, SETUP_DONE_MESSAGE)


def _verify_code(request: Request, settings: Settings, code: str) -> None:
    """Kodu sınar. Hatalı denemeler giriş denemeleriyle aynı sayaca yazılır."""
    throttle = login_throttle(request.app)
    key = client_key(request)
    now = time.monotonic()
    if throttle.is_blocked(key, now):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS_MESSAGE)
    if not check_setup_code(settings, code):
        throttle.record_failure(key, now)
        logger.warning("Hatalı kurulum kodu denemesi: %s", key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_SETUP_CODE_MESSAGE)


@router.get("/setup", response_model=SetupStatusOut)
async def read_setup(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SetupStatusOut:
    required = await setup_required(session)
    if required:
        ensure_setup_code(settings)
    return SetupStatusOut(required=required)


@router.post("/setup/verify", response_model=list[SetupPersonOut])
async def verify_setup(
    payload: SetupCodeIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[SetupPersonOut]:
    """Kod doğruysa sahiplenilebilecek, girişi olmayan kişileri listeler."""
    await _require_setup(session)
    _verify_code(request, settings, payload.code)
    people = (
        await session.scalars(
            select(User)
            .where(User.is_active.is_(True), User.password_hash.is_(None))
            .order_by(User.id)
        )
    ).all()
    return [SetupPersonOut(id=person.id, display_name=person.display_name) for person in people]


@router.post("/setup", response_model=MeOut)
async def complete_setup(
    payload: SetupIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MeOut:
    await _require_setup(session)
    _verify_code(request, settings, payload.code)
    try:
        username = clean_username(payload.username)
        password = check_password(payload.password)
        if payload.user_id is None:
            user = User(
                display_name=clean_display_name(payload.display_name or ""),
                role=ROLE_OWNER,
            )
            session.add(user)
        else:
            user = await session.get(User, payload.user_id)
            if user is None or has_login(user):
                raise AccountError("Seçilen kişi bulunamadı.")
            if payload.display_name:
                user.display_name = clean_display_name(payload.display_name)
        await ensure_username_free(session, username, exclude_user_id=user.id)
    except AccountError as exc:
        raise _invalid(exc) from exc

    user.username = username
    user.password_hash = hash_password(password)
    user.is_admin = True
    user.is_active = True
    await session.commit()
    clear_setup_code(settings)
    set_session_cookie(response, request, settings, user)
    logger.info("İlk yönetici oluşturuldu: %s", user.display_name)
    return me_out(user, SOURCE_SESSION)


# ---------------------------------------------------------------------------
# Kisiler
# ---------------------------------------------------------------------------


class AdminUserOut(BaseModel):
    id: int
    display_name: str
    username: str | None
    is_admin: bool
    is_active: bool
    has_login: bool


class AdminUserCreateIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    is_admin: bool = False


class AdminUserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=256)
    is_admin: bool | None = None
    is_active: bool | None = None


async def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ADMIN_REQUIRED_MESSAGE)
    return user


def _admin_user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        display_name=user.display_name,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        has_login=has_login(user),
    )


@router.get("/admin/users", response_model=list[AdminUserOut])
async def list_users(
    _admin: User = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserOut]:
    users = (await session.scalars(select(User).order_by(User.id))).all()
    return [_admin_user_out(user) for user in users]


@router.post(
    "/admin/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: AdminUserCreateIn,
    admin: User = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    try:
        display_name = clean_display_name(payload.display_name)
        username = clean_username(payload.username)
        password = check_password(payload.password)
        await ensure_username_free(session, username)
    except AccountError as exc:
        raise _invalid(exc) from exc

    user = User(
        display_name=display_name,
        username=username,
        password_hash=hash_password(password),
        is_admin=payload.is_admin,
        role=ROLE_OWNER,
    )
    session.add(user)
    await session.commit()
    logger.info("%s yeni kişi ekledi: %s", admin.display_name, display_name)
    return _admin_user_out(user)


@router.patch("/admin/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: int,
    payload: AdminUserUpdateIn,
    request: Request,
    response: Response,
    admin: User = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AdminUserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kişi bulunamadı")

    is_self = user.id == admin.id
    if is_self and (payload.is_active is False or payload.is_admin is False):
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_LOCKOUT_MESSAGE)

    password_changed = False
    try:
        if payload.display_name is not None:
            user.display_name = clean_display_name(payload.display_name)
        if payload.username is not None:
            username = clean_username(payload.username)
            await ensure_username_free(session, username, exclude_user_id=user.id)
            user.username = username
        if payload.password is not None:
            user.password_hash = hash_password(check_password(payload.password))
            password_changed = True
        if (user.username is None) != (user.password_hash is None):
            raise AccountError(
                "Giriş için kullanıcı adı ve şifre birlikte belirlenmelidir."
            )
    except AccountError as exc:
        await session.rollback()
        raise _invalid(exc) from exc

    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active

    await session.flush()
    if await setup_required(session):
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMIN_MESSAGE)
    await session.commit()

    # Sifre degisince eski cerezler gecersiz olur; degistiren kisi kendisiyse
    # bu cihazdaki oturumu yeni sifreyle surdurulur.
    if is_self and password_changed and request.state.auth_source == SOURCE_SESSION:
        set_session_cookie(response, request, settings, user)
    logger.info("%s bir kişiyi güncelledi: %s", admin.display_name, user.display_name)
    return _admin_user_out(user)
