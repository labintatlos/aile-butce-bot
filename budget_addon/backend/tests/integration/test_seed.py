"""Başlangıç verisi testleri.

Seed her açılışta çalışacağı için idempotent olmak zorundadır: aksi halde
her yeniden başlatmada kayıt çoğalır ya da kullanıcının ayarları geri alınır.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import Category, PaymentMethod, User
from app.services.seed import DEFAULT_CATEGORIES, seed_all

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def settings():
    return Settings(
        authorized_telegram_ids="111,222",
        user_display_names="111:Aykut,222:Aslıhan",
        ha_user_map="70bbe879:111,6ab54aa0:222",
    )


async def test_seed_creates_the_expected_starting_data(async_session, settings):
    counts = await seed_all(async_session, settings)

    assert counts["categories"] == len(DEFAULT_CATEGORIES)
    assert counts["payment_methods"] == 4  # Nakit + 3 kart
    assert counts["users"] == 2

    names = set((await async_session.scalars(select(Category.name))).all())
    assert "Market" in names and "Diğer" in names


async def test_seed_is_idempotent(async_session, settings, count_rows):
    await seed_all(async_session, settings)
    first = await count_rows(Category), await count_rows(PaymentMethod)

    second_run = await seed_all(async_session, settings)

    assert second_run == {
        "categories": 0,
        "payment_methods": 0,
        "users": 0,
    }
    assert (await count_rows(Category), await count_rows(PaymentMethod)) == first


async def test_seed_does_not_overwrite_user_edits(async_session, settings):
    await seed_all(async_session, settings)

    card = await async_session.scalar(
        select(PaymentMethod).where(PaymentMethod.name == "Aykut Kredi Kartı 1")
    )
    card.statement_day = 26
    market = await async_session.scalar(
        select(Category).where(Category.name == "Market")
    )
    market.is_active = False
    await async_session.commit()

    await seed_all(async_session, settings)

    await async_session.refresh(card)
    await async_session.refresh(market)
    assert card.statement_day == 26
    assert market.is_active is False


async def test_users_come_from_configuration_not_from_code(async_session):
    settings = Settings(
        authorized_telegram_ids="999", user_display_names="999:Test Kullanıcı"
    )
    await seed_all(async_session, settings)

    users = (await async_session.scalars(select(User))).all()
    assert [u.telegram_user_id for u in users] == [999]
    assert users[0].display_name == "Test Kullanıcı"


async def test_home_assistant_ids_are_mapped_when_configured(async_session, settings):
    await seed_all(async_session, settings)

    aykut = await async_session.scalar(
        select(User).where(User.telegram_user_id == 111)
    )
    assert aykut.ha_user_id == "70bbe879"


async def test_seeded_cards_are_marked_as_needing_real_dates(async_session, settings):
    """Yer tutucu kart günleri kullanıcıya açıkça bildirilmelidir."""
    await seed_all(async_session, settings)

    cards = (
        await async_session.scalars(
            select(PaymentMethod).where(PaymentMethod.type == "credit_card")
        )
    ).all()
    assert len(cards) == 3
    assert all("ayarlar" in (card.notes or "").lower() for card in cards)


async def test_seed_without_configured_users_creates_none(async_session):
    counts = await seed_all(async_session, Settings(authorized_telegram_ids=""))
    assert counts["users"] == 0
