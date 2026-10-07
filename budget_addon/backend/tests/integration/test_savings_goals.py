"""Birikim hedefleri: aylık gereken tutar ve bu ayın kalanıyla karşılaştırma."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services import savings
from app.services.income import create_income
from tests.integration.test_receipt_upload import site  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio

OCTOBER_7 = date(2026, 10, 7)


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


def test_months_left_counts_this_month_and_the_target_month():
    assert savings.months_left(OCTOBER_7, date(2027, 6, 30)) == 9  # Eki…Haz
    assert savings.months_left(OCTOBER_7, date(2026, 10, 31)) == 1
    assert savings.months_left(OCTOBER_7, date(2026, 10, 7)) == 1
    assert savings.months_left(OCTOBER_7, date(2026, 10, 6)) == 0


def _status(target, saved, target_date, today=OCTOBER_7):
    return savings.GoalStatus(
        id=1,
        name="Tatil",
        target_minor=target,
        saved_minor=saved,
        target_date=target_date,
        months_left=savings.months_left(today, target_date),
    )


def test_the_monthly_amount_is_rounded_up_so_the_last_month_is_not_short():
    goal = _status(target=5_000_000, saved=0, target_date=date(2027, 6, 30))

    # 50.000 TL / 9 ay = 5.555,555… -> 5.555,56 TL
    assert goal.monthly_required_minor == 555_556
    assert goal.monthly_required_minor * 9 >= goal.remaining_minor


def test_what_is_already_saved_is_not_asked_for_again():
    goal = _status(target=5_000_000, saved=2_300_000, target_date=date(2027, 6, 30))

    assert goal.remaining_minor == 2_700_000
    assert goal.monthly_required_minor == 300_000
    assert goal.ratio == 46


def test_a_completed_goal_needs_nothing_more():
    goal = _status(target=100_000, saved=150_000, target_date=date(2027, 1, 1))

    assert goal.is_complete
    assert goal.remaining_minor == 0
    assert goal.monthly_required_minor == 0
    assert goal.ratio == 100


def test_a_goal_past_its_date_is_overdue_and_left_out_of_the_monthly_total():
    goal = _status(target=100_000, saved=10_000, target_date=date(2026, 9, 30))

    assert goal.is_overdue
    assert goal.monthly_required_minor == 0


# ---------------------------------------------------------------------------
# Bu ayin kalaniyla karsilastirma
# ---------------------------------------------------------------------------


async def test_without_income_the_month_is_not_compared(async_session, people):
    await savings.create_goal(
        async_session,
        user=people["aykut"],
        name="Tatil",
        target_minor=900_000,
        target_date=date(2027, 6, 30),
        today=OCTOBER_7,
    )

    report = await savings.overview(async_session, today=OCTOBER_7)

    assert report.monthly_required_minor == 100_000
    assert report.month_remaining_minor is None
    assert report.covers is None


async def test_the_months_remainder_is_compared_with_what_the_goals_need(
    async_session, people
):
    await create_income(
        async_session,
        user=people["aykut"],
        amount=150_000,
        received_date=OCTOBER_7,
        source="Maaş",
    )
    await savings.create_goal(
        async_session,
        user=people["aykut"],
        name="Tatil",
        target_minor=900_000,
        target_date=date(2027, 6, 30),
        today=OCTOBER_7,
    )
    await savings.create_goal(
        async_session,
        user=people["aslihan"],
        name="Araba",
        target_minor=1_200_000,
        target_date=date(2027, 9, 30),
        today=OCTOBER_7,
    )

    report = await savings.overview(async_session, today=OCTOBER_7)

    assert report.monthly_required_minor == 100_000 + 100_000
    assert report.month_remaining_minor == 150_000
    assert report.covers is False

    await create_income(
        async_session, user=people["aslihan"], amount=50_000, received_date=OCTOBER_7
    )
    report = await savings.overview(async_session, today=OCTOBER_7)
    assert report.covers is True


# ---------------------------------------------------------------------------
# Kayit islemleri
# ---------------------------------------------------------------------------


async def test_saving_and_withdrawing_is_recorded_in_the_audit_log(async_session, people):
    goal = await savings.create_goal(
        async_session,
        user=people["aykut"],
        name="  Tatil   fonu ",
        target_minor=500_000,
        target_date=date(2027, 6, 30),
        today=OCTOBER_7,
    )
    assert goal.name == "Tatil fonu"

    await savings.add_to_goal(async_session, user=people["aykut"], goal=goal, amount_minor=80_000)
    await savings.add_to_goal(
        async_session, user=people["aslihan"], goal=goal, amount_minor=-30_000
    )

    assert goal.saved_minor == 50_000
    entries = (
        await async_session.scalars(
            select(AuditLog).where(AuditLog.entity_type == savings.ENTITY_SAVINGS_GOAL)
        )
    ).all()
    assert [entry.action for entry in entries] == ["create", "update", "update"]


async def test_more_than_was_saved_cannot_be_withdrawn(async_session, people):
    goal = await savings.create_goal(
        async_session,
        user=people["aykut"],
        name="Tatil",
        target_minor=500_000,
        target_date=date(2027, 6, 30),
        today=OCTOBER_7,
        saved_minor=10_000,
    )

    with pytest.raises(savings.SavingsError):
        await savings.add_to_goal(
            async_session, user=people["aykut"], goal=goal, amount_minor=-10_001
        )
    assert goal.saved_minor == 10_000


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "   "},
        {"target_minor": 0},
        {"target_date": date(2026, 10, 6)},
    ],
)
async def test_invalid_goals_are_refused(async_session, people, changes):
    values = {
        "name": "Tatil",
        "target_minor": 100_000,
        "target_date": date(2027, 1, 1),
    } | changes

    with pytest.raises(savings.SavingsError):
        await savings.create_goal(
            async_session, user=people["aykut"], today=OCTOBER_7, **values
        )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def test_goals_are_managed_from_the_site(site):  # noqa: F811
    today = date.fromisoformat((await site.get("/api/bootstrap")).json()["today"])
    target_date = date(today.year + 1, today.month, 1)

    created = await site.post(
        "/api/savings-goals",
        json={"name": "Tatil", "target_minor": 1_300_000, "target_date": target_date.isoformat()},
    )
    assert created.status_code == 201, created.text
    goal = created.json()["goals"][0]
    assert goal["months_left"] == 13
    assert goal["monthly_required"]["minor"] == 100_000

    deposited = (
        await site.post(f"/api/savings-goals/{goal['id']}/deposits", json={"amount_minor": 260_000})
    ).json()["goals"][0]
    assert deposited["saved"]["minor"] == 260_000
    assert deposited["monthly_required"]["minor"] == 80_000

    renamed = (
        await site.patch(f"/api/savings-goals/{goal['id']}", json={"name": "Yaz tatili"})
    ).json()["goals"][0]
    assert renamed["name"] == "Yaz tatili"

    overdraw = await site.post(
        f"/api/savings-goals/{goal['id']}/deposits", json={"amount_minor": -999_999}
    )
    assert overdraw.status_code == 422

    assert (await site.delete(f"/api/savings-goals/{goal['id']}")).status_code == 204
    assert (await site.get("/api/savings-goals")).json()["goals"] == []
    assert (await site.delete(f"/api/savings-goals/{goal['id']}")).status_code == 404


async def test_goals_need_a_login(public_client):
    assert (await public_client.get("/api/savings-goals")).status_code == 401
