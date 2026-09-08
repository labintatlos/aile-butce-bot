"""Alembic ortamı.

Veritabanı adresi `alembic.ini` yerine uygulama yapılandırmasından okunur;
böylece göçler add-on içinde de, geliştirme ortamında da aynı veritabanına
uygulanır ve dosyaya sır yazılmaz.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.database import create_engine_for
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite ALTER TABLE destegi sinirlidir; batch modu Alembic'in tabloyu
        # yeniden olusturarak degisiklik uygulamasini saglar.
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    settings = get_settings()
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(lambda sync_conn: _configure(sync_conn))
        await connection.run_sync(lambda _: context.run_migrations())
        await connection.commit()
    await engine.dispose()


def run_migrations_online() -> None:
    engine = create_engine_for(get_settings())
    asyncio.run(_run_async_migrations(engine))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
