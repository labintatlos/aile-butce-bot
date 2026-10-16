"""Kurallar, toplu düzenleme, geri alma ve açıklama birleştirme."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import Expense, Rule
from app.services import bulk
from app.services import rules as rules_service
from app.services.category_suggest import suggest_category
from app.services.expenses import ExpenseInput, SplitInput, create_expense
from tests.conftest import AYKUT_HA_ID

pytestmark = pytest.mark.asyncio

HEADERS = {"X-Remote-User-Id": AYKUT_HA_ID}
OCT_5 = date(2026, 10, 5)


async def _expense(session, people, fixtures, description, *, category=None, amount="100"):
    return await create_expense(
        session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=(category or fixtures["category"]).id,
            transaction_date=OCT_5,
            amount=amount,
            description=description,
        ),
    )


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


async def test_a_rule_beats_history_in_category_suggestions(async_session, people, fixtures):
    await _expense(async_session, people, fixtures, "Shell")
    assert (await suggest_category(async_session, "SHELL")).id == fixtures["category"].id

    await rules_service.create_rule(
        async_session,
        user=people["aykut"],
        values={"pattern": "shell", "set_category_id": fixtures["fuel"].id},
    )
    assert (await suggest_category(async_session, "SHELL #yol")).id == fixtures["fuel"].id


async def test_a_rule_must_change_something(async_session, people):
    with pytest.raises(rules_service.RuleError, match="en az bir"):
        await rules_service.create_rule(
            async_session, user=people["aykut"], values={"pattern": "migros"}
        )


async def test_patterns_are_stored_simplified(async_session, people, fixtures):
    rule = await rules_service.create_rule(
        async_session,
        user=people["aykut"],
        values={"pattern": "  MİGROS  Kadıköy ", "set_category_id": fixtures["category"].id},
    )
    assert rule.pattern == "migros kadikoy"


async def test_a_rule_can_be_applied_to_past_expenses_and_undone(async_session, people, fixtures):
    first = await _expense(async_session, people, fixtures, "SHELL 1234 #yol")
    second = await _expense(async_session, people, fixtures, "Shell Benzin")
    untouched = await _expense(async_session, people, fixtures, "Opet")
    rule = await rules_service.create_rule(
        async_session,
        user=people["aykut"],
        values={
            "pattern": "shell",
            "set_category_id": fixtures["fuel"].id,
            "set_description": "Shell",
        },
    )

    result = await bulk.apply_rule(async_session, user=people["aykut"], rule_id=rule.id)
    assert sorted(result.changed) == sorted([first.id, second.id])

    rows = {
        row.id: row
        for row in (await async_session.scalars(select(Expense))).all()
    }
    assert rows[first.id].description == "Shell #yol"
    assert rows[first.id].category_id == fixtures["fuel"].id
    assert rows[untouched.id].category_id == fixtures["category"].id

    await bulk.revert(
        async_session,
        user=people["aykut"],
        items=[
            {
                "expense_id": item.expense_id,
                "category_id": item.category_id,
                "description": item.description,
                "is_shared": item.is_shared,
                "owner_user_id": item.owner_user_id,
            }
            for item in result.previous
        ],
    )
    await async_session.refresh(rows[first.id])
    assert rows[first.id].description == "SHELL 1234 #yol"
    assert rows[first.id].category_id == fixtures["category"].id


# ---------------------------------------------------------------------------
# Toplu islemler
# ---------------------------------------------------------------------------


async def test_bulk_edit_changes_category_tags_and_owner_in_one_go(
    async_session, people, fixtures
):
    first = await _expense(async_session, people, fixtures, "market")
    second = await _expense(async_session, people, fixtures, None)

    result = await bulk.bulk_update(
        async_session,
        user=people["aykut"],
        ids=[first.id, second.id],
        changes={
            "category_id": fixtures["fuel"].id,
            "add_tag": "Tatil",
            "is_shared": False,
            "owner_user_id": people["aslihan"].id,
        },
    )

    assert sorted(result.changed) == sorted([first.id, second.id])
    for expense in (first, second):
        await async_session.refresh(expense)
        assert expense.category_id == fixtures["fuel"].id
        assert expense.owner_user_id == people["aslihan"].id
        assert expense.description.endswith("#tatil")


async def test_bulk_edit_skips_the_category_of_split_expenses(async_session, people, fixtures):
    split = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=OCT_5,
            amount="200",
            splits=(
                SplitInput(category_id=fixtures["category"].id, amount="150"),
                SplitInput(category_id=fixtures["fuel"].id, amount="50"),
            ),
        ),
    )
    result = await bulk.bulk_update(
        async_session,
        user=people["aykut"],
        ids=[split.id],
        changes={"category_id": fixtures["fuel"].id},
    )
    assert result.changed == []
    assert split.id in result.skipped


async def test_removing_a_tag_leaves_the_rest_of_the_description(async_session, people, fixtures):
    expense = await _expense(async_session, people, fixtures, "Otel #tatil #yaz")
    await bulk.bulk_update(
        async_session, user=people["aykut"], ids=[expense.id], changes={"remove_tag": "tatil"}
    )
    await async_session.refresh(expense)
    assert expense.description == "Otel #yaz"


async def test_bulk_delete_can_be_undone(async_session, people, fixtures):
    first = await _expense(async_session, people, fixtures, "a")
    second = await _expense(async_session, people, fixtures, "b")

    await bulk.bulk_delete(async_session, user=people["aykut"], ids=[first.id, second.id])
    await async_session.refresh(first)
    assert first.deleted_at is not None

    restored = await bulk.bulk_restore(
        async_session, user=people["aykut"], ids=[first.id, second.id]
    )
    assert sorted(restored.changed) == sorted([first.id, second.id])
    await async_session.refresh(first)
    assert first.deleted_at is None


# ---------------------------------------------------------------------------
# Aciklama birlestirme
# ---------------------------------------------------------------------------


async def test_differently_written_descriptions_are_grouped(async_session, people, fixtures):
    await _expense(async_session, people, fixtures, "MIGROS", amount="100")
    await _expense(async_session, people, fixtures, "Migros #tatil", amount="50")
    await _expense(async_session, people, fixtures, "migros kadıköy", amount="20")

    groups = await bulk.description_groups(async_session, query="migr")
    assert [(group.key, group.count, group.total_minor) for group in groups] == [
        ("migros", 2, 15_000),
        ("migros kadikoy", 1, 2_000),
    ]


async def test_merging_renames_keeps_tags_and_learns_a_rule(async_session, people, fixtures):
    tagged = await _expense(async_session, people, fixtures, "MIGROS 1234 #tatil")
    other = await _expense(async_session, people, fixtures, "migros kadıköy")

    result = await bulk.merge_descriptions(
        async_session,
        user=people["aykut"],
        keys=["migros 1234", "migros kadikoy"],
        target="Migros",
        create_rule=True,
    )

    assert sorted(result.changed) == sorted([tagged.id, other.id])
    await async_session.refresh(tagged)
    await async_session.refresh(other)
    assert tagged.description == "Migros #tatil"
    assert other.description == "Migros"
    learned = (await async_session.scalars(select(Rule).order_by(Rule.pattern))).all()
    assert [(rule.pattern, rule.set_description) for rule in learned] == [
        ("migros 1234", "Migros"),
        ("migros kadikoy", "Migros"),
    ]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def test_bulk_routes_are_not_mistaken_for_an_expense_id(
    client, seeded_users, seeded_reference_data
):
    created = await client.post(
        "/api/expenses",
        headers=HEADERS,
        json={
            "payment_method_id": seeded_reference_data["cash_id"],
            "category_id": seeded_reference_data["category_id"],
            "transaction_date": "2026-10-05",
            "amount": "75",
        },
    )
    expense_id = created.json()["id"]

    deleted = await client.post(
        "/api/expenses/bulk/delete", headers=HEADERS, json={"ids": [expense_id]}
    )
    assert deleted.status_code == 200, deleted.text
    restored = await client.post(
        "/api/expenses/bulk/restore", headers=HEADERS, json={"ids": [expense_id]}
    )
    assert restored.json()["changed"] == [expense_id]

    await client.delete(f"/api/expenses/{expense_id}", headers=HEADERS)
    single = await client.post(f"/api/expenses/{expense_id}/restore", headers=HEADERS)
    assert single.status_code == 200
    assert single.json()["id"] == expense_id


async def test_split_expenses_round_trip_over_http(client, seeded_users, seeded_reference_data):
    response = await client.post(
        "/api/expenses",
        headers=HEADERS,
        json={
            "payment_method_id": seeded_reference_data["cash_id"],
            "category_id": seeded_reference_data["category_id"],
            "transaction_date": "2026-10-05",
            "amount": "1.000",
            "splits": [
                {"category_id": seeded_reference_data["category_id"], "amount": "600"},
                {"category_id": seeded_reference_data["category_id"], "amount": "400"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert [part["amount"]["minor"] for part in body["splits"]] == [60_000, 40_000]

    cleared = await client.patch(
        f"/api/expenses/{body['id']}", headers=HEADERS, json={"splits": []}
    )
    assert cleared.json()["splits"] == []
