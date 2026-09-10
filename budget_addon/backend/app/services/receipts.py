"""Fiş fotoğrafları.

Fotoğraf veri dizinindeki `receipts/` klasörüne rastgele bir adla yazılır;
harcamada yalnızca dosya adı tutulur. Klasör doğrudan sunulmaz, fotoğrafa
yalnızca giriş yapmış kişi API üzerinden erişir. Home Assistant yedeği veri
dizininin tamamını aldığı için fişler de yedeğe girer.

Tutar fotoğraftan okunmaz: fiş yalnızca kanıttır.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models.audit_log import ACTION_UPDATE, ENTITY_EXPENSE
from ..models.expense import Expense
from ..models.user import User
from .audit import record_audit

RECEIPTS_DIRNAME = "receipts"
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class ReceiptError(ValueError):
    """Kullanıcıya olduğu gibi gösterilebilecek hata."""


def receipts_dir(settings: Settings) -> Path:
    return Path(settings.database_path).parent / RECEIPTS_DIRNAME


def detect_extension(data: bytes) -> str:
    """Türü dosya adından veya başlıktan değil, içeriğin kendisinden anlar."""
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ReceiptError("Fiş fotoğrafı JPEG, PNG veya WebP olmalıdır.")


def receipt_file(settings: Settings, expense: Expense) -> Path | None:
    if not expense.receipt_path:
        return None
    # Yalnizca dosya adi kullanilir: veritabanindaki deger klasor disina cikamaz.
    path = receipts_dir(settings) / Path(expense.receipt_path).name
    return path if path.is_file() else None


async def save_receipt(
    session: AsyncSession, settings: Settings, *, user: User, expense: Expense, data: bytes
) -> Expense:
    if not data:
        raise ReceiptError("Fotoğraf boş.")
    if len(data) > MAX_RECEIPT_BYTES:
        raise ReceiptError("Fotoğraf 10 MB'tan büyük olamaz.")
    extension = detect_extension(data)

    directory = receipts_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}{extension}"
    (directory / name).write_bytes(data)

    previous = expense.receipt_path
    try:
        await _set_receipt(session, user=user, expense=expense, name=name)
    except Exception:
        (directory / name).unlink(missing_ok=True)
        raise
    _remove_file(directory, previous)
    return expense


async def remove_receipt(
    session: AsyncSession, settings: Settings, *, user: User, expense: Expense
) -> None:
    previous = expense.receipt_path
    if previous is None:
        return
    await _set_receipt(session, user=user, expense=expense, name=None)
    _remove_file(receipts_dir(settings), previous)


async def _set_receipt(
    session: AsyncSession, *, user: User, expense: Expense, name: str | None
) -> None:
    before = {"receipt_path": expense.receipt_path}
    expense.receipt_path = name
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_EXPENSE,
            entity_id=expense.id,
            action=ACTION_UPDATE,
            old_data=before,
            new_data={"receipt_path": name},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def _remove_file(directory: Path, name: str | None) -> None:
    if name:
        (directory / Path(name).name).unlink(missing_ok=True)
