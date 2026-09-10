"""Kullanıcı adı, şifre ve isim kuralları.

Kişiler sitedeki yönetici ekranından yönetilir. Aynı kurallar ilk kurulumda,
yönetici ekranında ve kişinin kendi şifresini değiştirirken uygulanır; hata
mesajları doğrudan kullanıcıya gösterilir.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User

USERNAME_PATTERN = re.compile(r"[a-z0-9._-]{3,32}")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
MAX_DISPLAY_NAME_LENGTH = 64


class AccountError(ValueError):
    """Kullanıcıya olduğu gibi gösterilebilecek doğrulama hatası."""


def clean_username(raw: str) -> str:
    username = raw.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AccountError(
            "Kullanıcı adı 3-32 karakter olmalı; Türkçe karakter kullanmadan harf, "
            "rakam, nokta, alt çizgi veya tire içerebilir."
        )
    return username


def check_password(raw: str) -> str:
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Şifre en az {MIN_PASSWORD_LENGTH} karakter olmalıdır.")
    if len(raw) > MAX_PASSWORD_LENGTH:
        raise AccountError("Şifre çok uzun.")
    return raw


def clean_display_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise AccountError("İsim boş bırakılamaz.")
    if len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise AccountError(
            f"İsim en fazla {MAX_DISPLAY_NAME_LENGTH} karakter olabilir."
        )
    return name


async def ensure_username_free(
    session: AsyncSession, username: str, *, exclude_user_id: int | None = None
) -> None:
    query = select(User.id).where(User.username == username)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    if await session.scalar(query) is not None:
        raise AccountError("Bu kullanıcı adı başka bir kişide kullanılıyor.")


def has_login(user: User) -> bool:
    return user.username is not None and user.password_hash is not None
