"""Başlangıç verisi testleri.

Seed her açılışta çalışacağı için idempotent olmak zorundadır: aksi halde
her yeniden başlatmada kayıt çoğalır ya da kullanıcının ayarları geri alınır.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import Category, PaymentMethod, User
from app.services.seed import DEFAULT_CATEGORIES, DEFAULT_CARD_NAMES, seed_all
from app.services.settings_service import delete_payment_method, update_payment_method

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def settings():
    return Settings(_env_file=None)


async def test_seed_creates_the_expected_starting_data(async_session, settings):
    counts = await seed_all(async_session, settings)

    assert counts["categories"] == len(DEFAULT_CATEGORIES)
    assert counts["payment_methods"] == 4  # Nakit + 3 kart

    names = set((await async_session.scalars(select(Category.name))).all())
    assert "Market" in names and "Diğer" in names


async def test_seed_is_idempotent(async_session, settings, count_rows):
    await seed_all(async_session, settings)
    first = await count_rows(Category), await count_rows(PaymentMethod)

    second_run = await seed_all(async_session, settings)

    assert second_run == {"categories": 0, "payment_methods": 0}
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


async def test_deleted_starter_card_is_not_recreated_on_next_start(
    async_session, settings
):
    """Açılış seed'i, kullanıcının sildiği örnek kartı geri getirmemelidir."""
    await seed_all(async_session, settings)
    user = User(display_name="Yönetici", username="admin", is_admin=True)
    async_session.add(user)
    await async_session.commit()
    card = await async_session.scalar(
        select(PaymentMethod).where(PaymentMethod.name == DEFAULT_CARD_NAMES[0])
    )

    await delete_payment_method(async_session, user=user, method=card)
    counts = await seed_all(async_session, settings)

    assert counts["payment_methods"] == 0
    assert await async_session.scalar(
        select(PaymentMethod).where(PaymentMethod.name == DEFAULT_CARD_NAMES[0])
    ) is None


async def test_renamed_starter_card_is_not_duplicated_on_next_start(
    async_session, settings
):
    await seed_all(async_session, settings)
    user = User(display_name="Yönetici", username="admin", is_admin=True)
    async_session.add(user)
    await async_session.commit()
    card = await async_session.scalar(
        select(PaymentMethod).where(PaymentMethod.name == DEFAULT_CARD_NAMES[0])
    )

    await update_payment_method(
        async_session, user=user, method=card, changes={"name": "Kişisel Kartım"}
    )
    await seed_all(async_session, settings)

    names = set((await async_session.scalars(select(PaymentMethod.name))).all())
    assert "Kişisel Kartım" in names
    assert DEFAULT_CARD_NAMES[0] not in names


async def test_people_are_created_on_the_site_not_by_seed(async_session, settings):
    """İlk yönetici kurulum ekranında oluşturulur; seed kimseyi uydurmaz."""
    await seed_all(async_session, settings)
    assert (await async_session.scalars(select(User))).all() == []


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
