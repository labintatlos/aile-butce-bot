"""İlk yönetici kurulumu.

Site ilk açıldığında hiç yönetici yoktur. Kurulum formu internete açık bir
adreste durduğu için onu adresi bulan herkes değil, yalnızca eklentinin sahibi
doldurabilmelidir: tek kullanımlık bir kod üretilip eklenti günlüğüne yazılır
ve form bu kodu ister. Günlüğü yalnızca Home Assistant'a giriş yapabilen kişi
görür.

Kod veri dizininde durur, böylece yeniden başlatmada değişmez; ilk yönetici
oluşturulunca silinir.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models.user import User
from .sessions import create_file_once

logger = logging.getLogger(__name__)

SETUP_CODE_FILE_NAME = "setup_code"


def _code_path(settings: Settings) -> Path:
    return Path(settings.database_path).parent / SETUP_CODE_FILE_NAME


def _digits(code: str) -> str:
    return "".join(character for character in code if character.isdigit())


async def setup_required(session: AsyncSession) -> bool:
    """Giriş yapabilen etkin bir yönetici yoksa kurulum gerekir."""
    admin_id = await session.scalar(
        select(User.id)
        .where(
            User.is_admin.is_(True),
            User.is_active.is_(True),
            User.username.is_not(None),
            User.password_hash.is_not(None),
        )
        .limit(1)
    )
    return admin_id is None


def announce_setup_code(code: str) -> None:
    logger.warning(
        "İlk yönetici henüz oluşturulmadı. Siteyi açın ve şu kurulum kodunu "
        "girin: %s",
        code,
    )


def ensure_setup_code(settings: Settings) -> str:
    """Kurulum kodunu döndürür; yoksa üretir ve günlüğe yazar."""
    path = _code_path(settings)
    if not path.exists():
        digits = f"{secrets.randbelow(10**8):08d}"
        if create_file_once(path, f"{digits[:4]}-{digits[4:]}"):
            announce_setup_code(path.read_text(encoding="ascii").strip())
    return path.read_text(encoding="ascii").strip()


def check_setup_code(settings: Settings, code: str) -> bool:
    path = _code_path(settings)
    if not path.exists():
        return False
    expected = _digits(path.read_text(encoding="ascii"))
    return bool(expected) and hmac.compare_digest(_digits(code), expected)


def clear_setup_code(settings: Settings) -> None:
    _code_path(settings).unlink(missing_ok=True)
