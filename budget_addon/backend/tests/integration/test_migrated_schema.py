"""Şemayı **göçlerle** kuran testler.

Diğer testler şemayı `Base.metadata.create_all` ile kurar. Üretimde şema
Alembic göçleriyle kurulur ve ikisi ayrışabilir: bir göç sütun varsayılanını
veya kısıtını taşımayı unutursa testler yeşil kalırken eklenti açılışta düşer.

Nitekim bu gerçekleşti. `payment_methods` tablosunu yeniden oluşturan göç
`created_at` sütununun `server_default` değerini taşımıyordu; tüm birim ve
entegrasyon testleri geçtiği hâlde eklenti seed sırasında
"NOT NULL constraint failed: payment_methods.created_at" ile çöküyordu.

Bu dosya o boşluğu kapatır: gerçek göçleri gerçek bir dosya üzerinde çalıştırır
ve uygulamanın açılış yolunu (seed + harcama oluşturma) o şema üzerinde dener.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import Settings
from app.models import Expense, PaymentMethod
from app.models.payment_method import TYPE_CREDIT_CARD
from app.services.expenses import ExpenseInput, create_expense
from app.services.seed import seed_all
from app.services.settings_service import create_payment_method

pytestmark = pytest.mark.asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def migrated_database(tmp_path, monkeypatch):
    """Alembic göçleriyle kurulmuş boş bir veritabanı."""
    database_path = tmp_path / "budget.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))

    from app.config import get_settings

    get_settings.cache_clear()

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")

    yield database_path
    get_settings.cache_clear()


@pytest.fixture()
async def migrated_session(migrated_database):
    engine = create_async_engine(f"sqlite+aiosqlite:///{migrated_database}")
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture()
def settings():
    return Settings(
        _env_file=None,
        authorized_telegram_ids="111,222",
        user_display_names="111:Aykut,222:Aslıhan",
    )


async def test_seed_runs_against_the_migrated_schema(migrated_session, settings):
    """Eklentinin açılışta yaptığı işin aynısı: göç, sonra seed."""
    counts = await seed_all(migrated_session, settings)

    assert counts["categories"] == 16
    assert counts["payment_methods"] == 4
    assert counts["users"] == 2


async def test_timestamps_are_filled_in_on_the_migrated_schema(
    migrated_session, settings
):
    """Eksik bir sütun varsayılanı tam olarak burada ortaya çıkar."""
    await seed_all(migrated_session, settings)

    cash = await migrated_session.scalar(
        select(PaymentMethod).where(PaymentMethod.name == "Nakit")
    )
    assert cash.created_at is not None
    assert cash.updated_at is not None


async def test_an_expense_can_be_recorded_on_the_migrated_schema(
    migrated_session, settings
):
    """Açılıştan ilk harcamaya kadar olan yolun tamamı."""
    await seed_all(migrated_session, settings)

    from app.models.category import Category
    from app.models.user import User

    user = await migrated_session.scalar(select(User))
    category = await migrated_session.scalar(select(Category))
    card = await create_payment_method(
        migrated_session,
        user=user,
        name="Test Kartı",
        type=TYPE_CREDIT_CARD,
        statement_day=26,
    )

    expense = await create_expense(
        migrated_session,
        user=user,
        data=ExpenseInput(
            payment_method_id=card.id,
            category_id=category.id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )

    assert expense.public_id == "EXP-000001"
    assert len(expense.installments) == 3
    assert sum(line.amount_minor for line in expense.installments) == 300_000
    # Kesim 26 -> ekstre 26 Eylul, +10 gun = 6 Ekim (sali)
    assert expense.installments[0].statement_date == date(2026, 9, 26)
    assert expense.installments[0].due_date == date(2026, 10, 6)


async def test_check_constraints_survive_the_migrations(migrated_session, settings):
    """Göçler tabloyu yeniden oluştururken kısıtları kaybetmemelidir."""
    from sqlalchemy.exc import IntegrityError

    await seed_all(migrated_session, settings)
    migrated_session.add(
        PaymentMethod(name="Vadesi Bozuk", type=TYPE_CREDIT_CARD, statement_day=10, due_offset_days=0)
    )
    with pytest.raises(IntegrityError):
        await migrated_session.commit()


async def test_the_migrated_schema_has_no_leftover_due_day_column(migrated_database):
    import sqlite3

    connection = sqlite3.connect(migrated_database)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(payment_methods)")}
    finally:
        connection.close()

    assert "due_offset_days" in columns
    assert "due_day" not in columns


async def test_no_expenses_exist_in_a_fresh_installation(migrated_session, settings):
    await seed_all(migrated_session, settings)
    assert await migrated_session.scalar(select(Expense)) is None


async def test_the_migrated_schema_carries_the_reminder_tables(migrated_database):
    """Hatırlatma göçü gerçek göç zincirinde de uygulanmalıdır."""
    import sqlite3

    connection = sqlite3.connect(migrated_database)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    finally:
        connection.close()

    assert "notification_log" in tables
    assert "reminders_enabled" in user_columns
