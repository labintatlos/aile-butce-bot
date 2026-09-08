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


# --------------------------------------------------------------------------
# HTTP istemcileri: kimlik dogrulama yolunu uctan uca sinamak icin
# --------------------------------------------------------------------------

TEST_BOT_TOKEN = "123456:TEST-TOKEN-ONLY"
AYKUT_TELEGRAM_ID = 111
ASLIHAN_TELEGRAM_ID = 222
AYKUT_HA_ID = "70bbe879b6f145d9ba41e2ae8e2b81aa"
ASLIHAN_HA_ID = "6ab54aa06b034eb6b80c7956c66fbf3b"


def _test_settings(**overrides):
    from app.config import Settings

    defaults = dict(
        telegram_bot_token=TEST_BOT_TOKEN,
        authorized_telegram_ids=f"{AYKUT_TELEGRAM_ID},{ASLIHAN_TELEGRAM_ID}",
        user_display_names=f"{AYKUT_TELEGRAM_ID}:Aykut,{ASLIHAN_TELEGRAM_ID}:Aslıhan",
        ha_user_map=f"{AYKUT_HA_ID}:{AYKUT_TELEGRAM_ID},{ASLIHAN_HA_ID}:{ASLIHAN_TELEGRAM_ID}",
        debug=False,
        allow_dev_auth=False,
        trust_ingress_headers=True,
        _env_file=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _build_client(async_engine, settings):
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

    from app.config import get_settings
    from app.database import get_session
    from app.main import create_app

    app = create_app(settings)

    async def _session_override():
        async with _AsyncSession(async_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: settings
    # ASGITransport lifespan calistirmaz; seed testte acikca yapilir.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest_asyncio.fixture()
async def client(async_engine):
    """Ingress basligina guvenen ornek (add-on ici)."""
    async with _build_client(async_engine, _test_settings()) as client:
        yield client


@pytest_asyncio.fixture()
async def public_client(async_engine):
    """Internete acik ornek: Ingress basligina guvenmez."""
    settings = _test_settings(trust_ingress_headers=False)
    async with _build_client(async_engine, settings) as client:
        yield client


@pytest_asyncio.fixture()
async def dev_client(async_engine):
    """Yerel gelistirme ornegi: dev basligi acik."""
    settings = _test_settings(allow_dev_auth=True)
    async with _build_client(async_engine, settings) as client:
        yield client


@pytest_asyncio.fixture()
async def seeded_users(async_session):
    aykut = User(
        telegram_user_id=AYKUT_TELEGRAM_ID,
        ha_user_id=AYKUT_HA_ID,
        display_name="Aykut",
        role=ROLE_OWNER,
    )
    aslihan = User(
        telegram_user_id=ASLIHAN_TELEGRAM_ID,
        ha_user_id=ASLIHAN_HA_ID,
        display_name="Aslıhan",
        role=ROLE_OWNER,
    )
    async_session.add_all([aykut, aslihan])
    await async_session.commit()
    return {"aykut": aykut, "aslihan": aslihan}


@pytest_asyncio.fixture()
async def seeded_reference_data(async_session):
    category = Category(name="Market", emoji="🛒", sort_order=1)
    cash = PaymentMethod(name="Nakit", type=TYPE_CASH)
    card = PaymentMethod(
        name="Aslıhan Kredi Kartı 1",
        type=TYPE_CREDIT_CARD,
        statement_day=10,
        due_day=20,
    )
    async_session.add_all([category, cash, card])
    await async_session.commit()
    return {"category_id": category.id, "cash_id": cash.id, "card_id": card.id}
