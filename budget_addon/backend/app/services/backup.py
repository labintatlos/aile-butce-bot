"""Veritabanı yedekleme.

Çalışan bir SQLite dosyasını `cp` ile kopyalamak güvenli değildir: kopyalama
sırasında yazılan bir işlem, yarısı eski yarısı yeni bir dosya bırakabilir ve
WAL modunda yan dosyalar kopyalanmazsa yedek eksik olur.

Bunun yerine SQLite'ın kendi yedekleme API'si (`Connection.backup`) kullanılır;
tutarlı bir anlık görüntü üretir ve veritabanı açıkken çalışır.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..utils.time import DEFAULT_TIMEZONE, local_now

logger = logging.getLogger(__name__)

BACKUP_PREFIX = "budget"
BACKUP_SUFFIX = ".db"
TIMESTAMP_FORMAT = "%Y-%m-%d-%H%M%S"
DEFAULT_BACKUP_DIRNAME = "backups"


class BackupError(RuntimeError):
    """Yedekleme tamamlanamadı."""


@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    size_bytes: int
    removed: tuple[Path, ...]


def backup_filename(moment: datetime | None = None, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    """`budget-2026-09-02-230000.db`"""
    stamp = (moment or local_now(timezone_name)).strftime(TIMESTAMP_FORMAT)
    return f"{BACKUP_PREFIX}-{stamp}{BACKUP_SUFFIX}"


def existing_backups(directory: Path) -> list[Path]:
    """Yedekleri eskiden yeniye sıralar."""
    if not directory.exists():
        return []
    pattern = f"{BACKUP_PREFIX}-*{BACKUP_SUFFIX}"
    return sorted(directory.glob(pattern), key=lambda path: path.name)


def apply_retention(directory: Path, keep: int) -> tuple[Path, ...]:
    """En yeni `keep` adet yedeği bırakır, eskileri siler."""
    if keep < 1:
        raise ValueError("Saklanacak yedek sayısı en az 1 olmalıdır")
    backups = existing_backups(directory)
    surplus = backups[: max(0, len(backups) - keep)]
    for path in surplus:
        path.unlink(missing_ok=True)
        logger.info("Eski yedek silindi: %s", path.name)
    return tuple(surplus)


def create_backup(
    database_path: str | Path,
    directory: str | Path | None = None,
    *,
    keep: int = 14,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> BackupResult:
    """Tutarlı bir yedek alır ve saklama kuralını uygular."""
    source = Path(database_path)
    if not source.exists():
        raise BackupError(f"Veritabanı bulunamadı: {source}")

    target_dir = Path(directory) if directory else source.parent / DEFAULT_BACKUP_DIRNAME
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / backup_filename(timezone_name=timezone_name)

    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        destination = sqlite3.connect(target)
        try:
            # SQLite'in kendi yedekleme mekanizmasi: tutarli anlik goruntu.
            connection.backup(destination)
        finally:
            destination.close()
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise BackupError(f"Yedekleme başarısız: {exc}") from exc
    finally:
        connection.close()

    removed = apply_retention(target_dir, keep)
    result = BackupResult(path=target, size_bytes=target.stat().st_size, removed=removed)
    logger.info("Yedek alındı: %s (%d bayt)", target.name, result.size_bytes)
    return result
