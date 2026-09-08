"""Alembic ortamı.

Veritabanı adresi `alembic.ini` yerine uygulama yapılandırmasından okunur;
böylece göçler add-on içinde de, geliştirme ortamında da aynı veritabanına
uygulanır ve dosyaya sır yazılmaz.
"""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger("alembic.env")


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


BATCH_TEMP_PREFIX = "_alembic_tmp_"


def recover_interrupted_batch(connection) -> None:
    """Yarım kalmış bir batch göçünden kurtarır.

    SQLite sütun silemediği için Alembic tabloyu `_alembic_tmp_<ad>` adıyla
    yeniden oluşturur, veriyi kopyalar, eskisini siler ve yenisini adlandırır.
    SQLite'ta DDL işlemleri Alembic tarafından transaction dışında sayıldığı
    için, süreç bu adımların ortasında ölürse geçici tablo geride kalır ve
    sonraki her deneme "table _alembic_tmp_... already exists" ile düşer.
    Home Assistant'ın watchdog'u eklentiyi saniyeler içinde yeniden
    başlattığından bu durum kolayca oluşabiliyor.

    İki farklı yarım kalma durumu vardır ve ayrımı önemlidir:

    - Asıl tablo hâlâ duruyorsa geçici tablo yalnızca artıktır; silinir.
    - Asıl tablo yoksa veri **geçici tablodadır**; silmek veri kaybı olurdu,
      bu yüzden geçici tablo asıl adına taşınır.
    """
    rows = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
        (f"{BATCH_TEMP_PREFIX}%",),
    ).fetchall()

    for (temp_name,) in rows:
        original = temp_name[len(BATCH_TEMP_PREFIX):]
        exists = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (original,),
        ).fetchone()

        if exists:
            logger.warning(
                "Yarım kalmış göçten kalan %s tablosu siliniyor; %s yerinde.",
                temp_name,
                original,
            )
            connection.exec_driver_sql(f'DROP TABLE "{temp_name}"')
        else:
            logger.warning(
                "%s tablosu bulunamadı; veriyi taşımak için %s yeniden "
                "adlandırılıyor.",
                original,
                temp_name,
            )
            connection.exec_driver_sql(
                f'ALTER TABLE "{temp_name}" RENAME TO "{original}"'
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


def _check_foreign_keys(connection) -> None:
    """Göç sonrası bozuk yabancı anahtar kalmadığını doğrular.

    Göç sırasında zorlama kapatıldığı için, açmadan önce veriyi bir kez
    denetlemek gerekir; aksi halde bozukluk çok sonra, ilk yazma denemesinde
    ortaya çıkardı.
    """
    broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if broken:
        raise RuntimeError(
            f"Göç sonrası yabancı anahtar tutarsızlığı bulundu: {broken!r}"
        )


async def _run_async_migrations(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        # Yabancı anahtar zorlaması göç boyunca kapatılır. SQLite sütun
        # silemediği için Alembic tabloyu yeniden oluşturur ve bunu yaparken
        # eskisini DROP eder; `expenses` tablosu `payment_methods`e referans
        # verdiğinden zorlama açıkken bu DROP "FOREIGN KEY constraint failed"
        # ile düşer. Kapatma yalnızca bu bağlantıyı etkiler ve göç bitince
        # geri açılır.
        await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        # Kurtarma göçlerden ÖNCE çalışır: geride kalmış bir geçici tablo,
        # aksi halde her açılışta göçü aynı noktada düşürür.
        await connection.run_sync(recover_interrupted_batch)
        await connection.commit()
        await connection.run_sync(lambda sync_conn: _configure(sync_conn))
        await connection.run_sync(lambda _: context.run_migrations())
        await connection.commit()
        await connection.run_sync(_check_foreign_keys)
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    await engine.dispose()


def run_migrations_online() -> None:
    engine = create_engine_for(get_settings())
    asyncio.run(_run_async_migrations(engine))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
