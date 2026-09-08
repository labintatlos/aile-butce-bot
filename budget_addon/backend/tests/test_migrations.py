"""Göçlerin gerçek bir veritabanı üzerinde uçtan uca çalıştığını doğrular.

Buradaki testler alembic'i ayrı bir süreçte çalıştırır. Bunun sebebi, hatanın
yalnızca `migrations/env.py` gerçekten yüklendiğinde ortaya çıkmasıdır: göç
sırasında yabancı anahtar zorlaması kapatılmazsa, tabloyu yeniden oluşturan
batch göçü `expenses` tablosunun referansı yüzünden "FOREIGN KEY constraint
failed" ile düşer. Test süitinin geri kalanı şemayı `metadata.create_all` ile
kurduğu için bu yolu hiç çalıştırmaz.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

INITIAL_REVISION = "e14c14326370"

SEED_SQL = """
INSERT INTO users (id, telegram_user_id, display_name, role, is_active)
    VALUES (1, 111, 'A', 'admin', 1);
INSERT INTO categories (id, name, emoji, sort_order, is_active)
    VALUES (1, 'Market', 'x', 1, 1);
INSERT INTO payment_methods
    (id, name, type, owner_user_id, currency, statement_day, due_day,
     cutoff_inclusive, is_active)
    VALUES (1, 'Kart', 'credit_card', 1, 'TRY', 15, 25, 1, 1);
INSERT INTO expenses
    (id, public_id, created_by_user_id, payment_method_id, category_id,
     transaction_date, total_amount_minor, currency, installment_count,
     payment_method_type_snapshot, payment_method_name_snapshot,
     statement_day_snapshot, due_day_snapshot, cutoff_inclusive_snapshot)
    VALUES (1, 'abc', 1, 1, 1, '2026-01-05', 1000, 'TRY', 1, 'credit_card',
            'Kart', 15, 25, 1);
"""


def _alembic(db_path: Path, *args: str) -> None:
    environment = {
        **os.environ,
        "DATABASE_PATH": str(db_path),
        "PYTHONPATH": str(BACKEND_DIR),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic {' '.join(args)} başarısız:\n{result.stderr}")


def test_upgrade_head_with_existing_data(tmp_path: Path) -> None:
    """Verisi olan bir veritabanı en güncel şemaya taşınabilmelidir."""
    db_path = tmp_path / "budget.db"

    _alembic(db_path, "upgrade", INITIAL_REVISION)

    connection = sqlite3.connect(db_path)
    connection.executescript(SEED_SQL)
    connection.commit()
    connection.close()

    _alembic(db_path, "upgrade", "head")

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT statement_day, due_offset_days FROM payment_methods"
        ).fetchall() == [(15, 10)]
        # Harcama kaydı, altındaki tablo yeniden oluşturulmasına rağmen
        # kart kaydına bağlı kalmalıdır.
        assert connection.execute(
            "SELECT payment_method_id FROM expenses"
        ).fetchall() == [(1,)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_upgrade_head_is_repeatable(tmp_path: Path) -> None:
    """Göç ikinci kez çalıştırıldığında da düşmemelidir.

    Home Assistant eklentiyi her başlatışında göçleri uygular; ayrıca yarım
    kalmış bir göçten sonraki yeniden deneme de aynı yolu izler.
    """
    db_path = tmp_path / "budget.db"
    _alembic(db_path, "upgrade", "head")
    _alembic(db_path, "upgrade", "head")
