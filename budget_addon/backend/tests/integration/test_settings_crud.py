"""Kart ve kategori yönetimi testleri.

En kritik kural: harcamalarda kullanılan bir kart veya kategori **silinemez**.
Silinebilseydi, ona bağlı geçmiş harcamaların ödeme yöntemi ve kategorisi
okunamaz hâle gelir ve raporlar bozulurdu. Bu durumda pasife alma önerilir.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import Category, PaymentMethod
from app.models.payment_method import TYPE_CREDIT_CARD
from app.services.expenses import ExpenseInput, create_expense, soft_delete_expense
from app.services.settings_service import (
    SettingsError,
    create_category,
    create_payment_method,
    delete_category,
    delete_payment_method,
    list_categories,
    list_payment_methods,
    set_active,
    update_category,
    update_payment_method,
)

pytestmark = pytest.mark.asyncio


async def spend_with(session, user, *, method, category, amount="100"):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=method.id,
            category_id=category.id,
            transaction_date=date(2026, 9, 5),
            amount=amount,
        ),
    )


# ---------------------------------------------------------------------------
# Kart ekleme
# ---------------------------------------------------------------------------


async def test_a_card_can_be_added(async_session, people):
    card = await create_payment_method(
        async_session,
        user=people["aykut"],
        name="Aykut Kredi Kartı 2",
        type=TYPE_CREDIT_CARD,
        statement_day=26,
    )
    assert card.id is not None
    assert card.statement_day == 26
    assert card.due_offset_days == 10
    assert card.is_active is True


async def test_added_card_appears_in_the_active_list(async_session, people):
    await create_payment_method(
        async_session, user=people["aykut"], name="Yeni Kart",
        type=TYPE_CREDIT_CARD, statement_day=5,
    )
    names = {m.name for m in await list_payment_methods(async_session)}
    assert "Yeni Kart" in names


@pytest.mark.parametrize("statement_day", [0, 32, None])
async def test_a_card_with_an_invalid_statement_day_is_refused(
    async_session, people, statement_day
):
    with pytest.raises(SettingsError):
        await create_payment_method(
            async_session, user=people["aykut"], name="Bozuk Kart",
            type=TYPE_CREDIT_CARD, statement_day=statement_day,
        )


@pytest.mark.parametrize("offset_days", [0, 61])
async def test_an_invalid_due_offset_is_refused(async_session, people, offset_days):
    with pytest.raises(SettingsError):
        await create_payment_method(
            async_session, user=people["aykut"], name="Vadesi Bozuk",
            type=TYPE_CREDIT_CARD, statement_day=10, due_offset_days=offset_days,
        )


# ---------------------------------------------------------------------------
# Kart adi degistirme
# ---------------------------------------------------------------------------


async def test_a_card_can_be_renamed(async_session, people, fixtures):
    await update_payment_method(
        async_session, user=people["aykut"], method=fixtures["card"],
        changes={"name": "Aslıhan Bonus"},
    )
    assert fixtures["card"].name == "Aslıhan Bonus"


async def test_renaming_a_card_does_not_rewrite_past_expenses(
    async_session, people, fixtures
):
    """Geçmiş harcama, kaydedildiği andaki kart adını göstermeye devam eder."""
    expense = await spend_with(
        async_session, people["aykut"],
        method=fixtures["card"], category=fixtures["category"],
    )
    original_name = expense.payment_method_name_snapshot

    await update_payment_method(
        async_session, user=people["aykut"], method=fixtures["card"],
        changes={"name": "Tamamen Başka Ad"},
    )

    await async_session.refresh(expense)
    assert expense.payment_method_name_snapshot == original_name


async def test_two_cards_cannot_share_a_name(async_session, people, fixtures):
    with pytest.raises(SettingsError):
        await update_payment_method(
            async_session, user=people["aykut"], method=fixtures["other_card"],
            changes={"name": fixtures["card"].name},
        )


# ---------------------------------------------------------------------------
# Kart silme
# ---------------------------------------------------------------------------


async def test_an_unused_card_is_really_deleted(async_session, people, count_rows):
    card = await create_payment_method(
        async_session, user=people["aykut"], name="Kullanılmayan Kart",
        type=TYPE_CREDIT_CARD, statement_day=1,
    )
    before = await count_rows(PaymentMethod)

    await delete_payment_method(async_session, user=people["aykut"], method=card)

    assert await count_rows(PaymentMethod) == before - 1


async def test_a_card_in_use_cannot_be_deleted(async_session, people, fixtures):
    await spend_with(
        async_session, people["aykut"],
        method=fixtures["card"], category=fixtures["category"],
    )
    with pytest.raises(SettingsError) as error:
        await delete_payment_method(
            async_session, user=people["aykut"], method=fixtures["card"]
        )
    assert "pasife" in str(error.value)


async def test_a_softly_deleted_expense_still_protects_its_card(
    async_session, people, fixtures
):
    """Silinmiş harcama geri alınabilir; kartı kaldırmak bunu kırardı."""
    expense = await spend_with(
        async_session, people["aykut"],
        method=fixtures["card"], category=fixtures["category"],
    )
    await soft_delete_expense(async_session, user=people["aykut"], expense=expense)

    with pytest.raises(SettingsError):
        await delete_payment_method(
            async_session, user=people["aykut"], method=fixtures["card"]
        )


async def test_a_card_in_use_can_be_deactivated_instead(
    async_session, people, fixtures
):
    await spend_with(
        async_session, people["aykut"],
        method=fixtures["card"], category=fixtures["category"],
    )
    await set_active(
        async_session, user=people["aykut"], entity=fixtures["card"], active=False
    )

    active = {m.id for m in await list_payment_methods(async_session)}
    everything = {m.id for m in await list_payment_methods(async_session, include_inactive=True)}
    assert fixtures["card"].id not in active
    assert fixtures["card"].id in everything


async def test_a_deactivated_card_can_be_reactivated(async_session, people, fixtures):
    await set_active(
        async_session, user=people["aykut"], entity=fixtures["card"], active=False
    )
    await set_active(
        async_session, user=people["aykut"], entity=fixtures["card"], active=True
    )
    assert fixtures["card"].id in {m.id for m in await list_payment_methods(async_session)}


# ---------------------------------------------------------------------------
# Kategoriler
# ---------------------------------------------------------------------------


async def test_a_category_can_be_added_renamed_and_deleted(
    async_session, people, count_rows
):
    category = await create_category(
        async_session, user=people["aykut"], name="Sinema", emoji="🎬"
    )
    assert category.emoji == "🎬"

    await update_category(
        async_session, user=people["aykut"], category=category,
        changes={"name": "Sinema & Tiyatro"},
    )
    assert category.name == "Sinema & Tiyatro"

    before = await count_rows(Category)
    await delete_category(async_session, user=people["aykut"], category=category)
    assert await count_rows(Category) == before - 1


async def test_a_category_in_use_cannot_be_deleted(async_session, people, fixtures):
    await spend_with(
        async_session, people["aykut"],
        method=fixtures["cash"], category=fixtures["category"],
    )
    with pytest.raises(SettingsError) as error:
        await delete_category(
            async_session, user=people["aykut"], category=fixtures["category"]
        )
    assert "pasife" in str(error.value)


async def test_duplicate_category_names_are_refused(async_session, people, fixtures):
    with pytest.raises(SettingsError):
        await create_category(
            async_session, user=people["aykut"], name=fixtures["category"].name
        )


async def test_a_deactivated_category_is_hidden_but_history_survives(
    async_session, people, fixtures
):
    expense = await spend_with(
        async_session, people["aykut"],
        method=fixtures["cash"], category=fixtures["category"],
    )
    await set_active(
        async_session, user=people["aykut"], entity=fixtures["category"], active=False
    )

    visible = {c.id for c in await list_categories(async_session)}
    assert fixtures["category"].id not in visible

    stored = await async_session.scalar(
        select(Category).where(Category.id == expense.category_id)
    )
    assert stored is not None


# ---------------------------------------------------------------------------
# Denetim kaydi
# ---------------------------------------------------------------------------


async def test_every_settings_change_is_audited(async_session, people, count_rows):
    from app.models import AuditLog

    before = await count_rows(AuditLog)
    card = await create_payment_method(
        async_session, user=people["aykut"], name="Denetim Kartı",
        type=TYPE_CREDIT_CARD, statement_day=1,
    )
    await update_payment_method(
        async_session, user=people["aykut"], method=card, changes={"name": "Yeni Ad"}
    )
    await delete_payment_method(async_session, user=people["aykut"], method=card)

    assert await count_rows(AuditLog) == before + 3
