"""Yarım kalmış göçlerden kurtarma.

Üretimde şu oldu: eklenti başka bir sebeple çöküyordu, Home Assistant'ın
watchdog'u konteyneri saniyeler içinde yeniden başlatıyordu ve göç, SQLite'ın
tabloyu yeniden oluşturma adımlarının ortasında kesildi. Geriye
`_alembic_tmp_expenses` tablosu kaldı; sonraki her açılış
"table _alembic_tmp_expenses already exists" ile düştü ve eklenti bir daha
hiç açılamadı.

Bu dosya iki kurtarma senaryosunu da sabitler:

- Asıl tablo duruyorsa geçici tablo yalnızca artıktır ve silinir.
- Asıl tablo yoksa veri geçici tablodadır; silmek veri kaybı olurdu, bu yüzden
  geçici tablo asıl adına taşınır.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


@pytest.fixture()
def database(tmp_path, monkeypatch):
    path = tmp_path / "budget.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    from app.config import get_settings

    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()


def columns(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def stop_at_first_migration(path: Path) -> None:
    """Veritabanını ilk göçün uygulandığı noktaya getirir."""
    command.upgrade(alembic_config(), "e14c14326370")


def test_a_leftover_temp_table_is_cleared_and_the_migration_completes(database):
    """Kullanıcının başına gelen durumun birebir aynısı."""
    stop_at_first_migration(database)

    # Yarim kalan gocun biraktigi artik: gecici tablo var, asil tablo da duruyor.
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE _alembic_tmp_expenses (id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()
    assert "_alembic_tmp_expenses" in tables(database)

    command.upgrade(alembic_config(), "head")

    assert "_alembic_tmp_expenses" not in tables(database)
    assert "due_offset_days" in columns(database, "payment_methods")
    assert "due_day" not in columns(database, "payment_methods")


def test_data_is_rescued_when_the_original_table_is_gone(database):
    """Asıl tablo silinmiş, veri geçici tablodaysa taşınmalıdır."""
    stop_at_first_migration(database)

    # Gercek kesilmeyi taklit et: gecici tablo asil tablonun DDL'iyle kurulur
    # (birincil anahtar dahil), veri kopyalanir, asil tablo silinir ve surec
    # tam yeniden adlandirmadan once olur.
    connection = sqlite3.connect(database)
    ddl = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='categories'"
    ).fetchone()[0]
    connection.execute(ddl.replace("categories", "_alembic_tmp_categories", 1))
    connection.execute(
        "INSERT INTO _alembic_tmp_categories SELECT * FROM categories"
    )
    connection.execute(
        "INSERT INTO _alembic_tmp_categories (id, name, emoji, sort_order, is_active)"
        " VALUES (99, 'Kurtarilan', '', 1, 1)"
    )
    connection.execute("DROP TABLE categories")
    connection.commit()
    connection.close()

    command.upgrade(alembic_config(), "head")

    assert "categories" in tables(database)
    assert "_alembic_tmp_categories" not in tables(database)

    connection = sqlite3.connect(database)
    try:
        names = {row[0] for row in connection.execute("SELECT name FROM categories")}
    finally:
        connection.close()
    assert "Kurtarilan" in names


def test_migrating_twice_is_harmless(database):
    """Göç zaten uygulanmışsa tekrar çalıştırmak hata vermemelidir."""
    command.upgrade(alembic_config(), "head")
    command.upgrade(alembic_config(), "head")

    assert "due_offset_days" in columns(database, "payment_methods")


def test_a_half_applied_migration_can_be_finished(database):
    """Bir tablo taşınmış, diğeri taşınmamışken göç tamamlanabilmelidir."""
    stop_at_first_migration(database)

    # `expenses` tarafi elle uygulanmis gibi davranilir.
    connection = sqlite3.connect(database)
    connection.execute("ALTER TABLE expenses ADD COLUMN due_offset_days_snapshot INTEGER")
    connection.commit()
    connection.close()

    command.upgrade(alembic_config(), "head")

    assert "due_offset_days_snapshot" in columns(database, "expenses")
    assert "due_day_snapshot" not in columns(database, "expenses")
    assert "due_offset_days" in columns(database, "payment_methods")
