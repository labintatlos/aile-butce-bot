"""Veritabanı motoru ve oturum yönetimi.

SQLite varsayılanları bu uygulama için yetersizdir ve her bağlantıda açıkça
ayarlanır:

- `foreign_keys=ON`  : SQLite yabancı anahtarları varsayılan olarak zorlamaz.
- `journal_mode=WAL` : Okuma ve yazmanın birbirini kilitlememesi için.
- `busy_timeout`     : Kilit çakışmasında hemen hata vermek yerine beklemek için.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings

BUSY_TIMEOUT_MS = 5_000

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _apply_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_engine_for(settings: Settings) -> AsyncEngine:
    if settings.database_path != ":memory:":
        Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    event.listen(engine.sync_engine, "connect", _apply_pragmas)
    return engine


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine_for(get_settings())
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI bağımlılığı olarak kullanılır."""
    async with get_session_factory()() as session:
        yield session


async def verify_pragmas(session: AsyncSession) -> dict[str, object]:
    """Kurulum doğrulaması için etkin PRAGMA değerlerini okur."""
    values = {}
    for pragma in ("foreign_keys", "journal_mode", "busy_timeout"):
        result = await session.execute(text(f"PRAGMA {pragma}"))
        values[pragma] = result.scalar()
    return values


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
