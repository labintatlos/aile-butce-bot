"""Test altyapısı.

Testler bellek içi SQLite üzerinde çalışır. Yabancı anahtar zorlaması
SQLite'ta varsayılan olarak kapalıdır ve açılmazsa kısıtlar sessizce
uygulanmaz; bu yüzden her bağlantıda açıkça etkinleştirilir.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, Category, PaymentMethod, User
from app.models.payment_method import TYPE_CASH, TYPE_CREDIT_CARD
from app.models.user import ROLE_OWNER


def _enable_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


# --------------------------------------------------------------------------
# Senkron oturum: sema kisitlarini dogrudan sinayan testler icin
# --------------------------------------------------------------------------


@pytest.fixture()
def engine():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", _enable_foreign_keys)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as session:
        yield session


# --------------------------------------------------------------------------
# Asenkron oturum: servis katmani testleri icin
# --------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def async_engine():
    # StaticPool: bellek ici veritabaninin tum baglantilar arasinda paylasilmasi icin.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine.sync_engine, "connect", _enable_foreign_keys)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def async_session(async_engine):
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
        yield session


@pytest_asyncio.fixture()
async def people(async_session):
    aykut = User(telegram_user_id=111, display_name="Aykut", role=ROLE_OWNER)
    aslihan = User(telegram_user_id=222, display_name="Aslıhan", role=ROLE_OWNER)
    async_session.add_all([aykut, aslihan])
    await async_session.commit()
    return {"aykut": aykut, "aslihan": aslihan}


@pytest_asyncio.fixture()
async def fixtures(async_session, people):
    market = Category(name="Market", emoji="🛒", sort_order=1)
    fuel = Category(name="Yakıt", emoji="⛽", sort_order=2)
    cash = PaymentMethod(name="Nakit", type=TYPE_CASH)
    card = PaymentMethod(
        name="Aslıhan Kredi Kartı 1",
        type=TYPE_CREDIT_CARD,
        owner_user_id=people["aslihan"].id,
        statement_day=10,
        due_day=20,
    )
    other_card = PaymentMethod(
        name="Aykut Kredi Kartı 1",
        type=TYPE_CREDIT_CARD,
        owner_user_id=people["aykut"].id,
        statement_day=25,
        due_day=5,
    )
    async_session.add_all([market, fuel, cash, card, other_card])
    await async_session.commit()
    return {
        "category": market,
        "fuel": fuel,
        "cash": cash,
        "card": card,
        "other_card": other_card,
    }


@pytest_asyncio.fixture()
async def count_rows(async_session):
    async def _count(model) -> int:
        return await async_session.scalar(select(func.count()).select_from(model))

    return _count
