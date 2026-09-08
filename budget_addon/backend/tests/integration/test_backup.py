"""Yedekleme testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-B*)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from app.services.backup import (
    BackupError,
    apply_retention,
    backup_filename,
    create_backup,
    existing_backups,
)


@pytest.fixture()
def populated_database(tmp_path):
    path = tmp_path / "budget.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE expenses (id INTEGER PRIMARY KEY, amount_minor INTEGER)")
    connection.executemany(
        "INSERT INTO expenses (amount_minor) VALUES (?)", [(100_000,), (250_050,)]
    )
    connection.commit()
    connection.close()
    return path


def test_i_b1_backup_filename_follows_the_specification():
    name = backup_filename(datetime(2026, 9, 2, 23, 0, 0))
    assert name == "budget-2026-09-02-230000.db"


def test_i_b2_backup_contains_the_same_rows(populated_database, tmp_path):
    result = create_backup(populated_database, tmp_path / "backups")

    assert result.path.exists()
    connection = sqlite3.connect(result.path)
    try:
        rows = connection.execute(
            "SELECT amount_minor FROM expenses ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [(100_000,), (250_050,)]


def test_backup_works_while_the_database_is_open(populated_database, tmp_path):
    """Açık bir veritabanı yedeklenebilmelidir; uygulama durdurulmaz."""
    live = sqlite3.connect(populated_database)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("INSERT INTO expenses (amount_minor) VALUES (999)")
    live.commit()
    try:
        result = create_backup(populated_database, tmp_path / "backups")
    finally:
        live.close()

    connection = sqlite3.connect(result.path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        connection.close()
    assert count == 3


def test_i_b3_retention_keeps_only_the_newest(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir()
    for day in range(1, 6):
        (directory / f"budget-2026-09-0{day}-120000.db").write_bytes(b"x")

    removed = apply_retention(directory, keep=3)

    remaining = [path.name for path in existing_backups(directory)]
    assert len(removed) == 2
    assert remaining == [
        "budget-2026-09-03-120000.db",
        "budget-2026-09-04-120000.db",
        "budget-2026-09-05-120000.db",
    ]


def test_retention_leaves_everything_when_under_the_limit(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir()
    (directory / "budget-2026-09-01-120000.db").write_bytes(b"x")

    assert apply_retention(directory, keep=5) == ()
    assert len(existing_backups(directory)) == 1


def test_retention_refuses_to_delete_everything(tmp_path):
    with pytest.raises(ValueError):
        apply_retention(tmp_path, keep=0)


def test_retention_ignores_unrelated_files(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir()
    (directory / "budget-2026-09-01-120000.db").write_bytes(b"x")
    (directory / "notlar.txt").write_text("dokunma")

    apply_retention(directory, keep=1)

    assert (directory / "notlar.txt").exists()


def test_missing_database_is_reported_clearly(tmp_path):
    with pytest.raises(BackupError):
        create_backup(tmp_path / "yok.db", tmp_path / "backups")


def test_backup_directory_is_created_when_missing(populated_database, tmp_path):
    target = tmp_path / "derin" / "yol" / "backups"
    result = create_backup(populated_database, target)
    assert result.path.parent == target
