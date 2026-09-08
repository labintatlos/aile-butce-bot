"""Harcama yaşam döngüsü testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-L*)."""

from __future__ import annotations

from datetime import date

import pytest

from app.models import AuditLog, Expense, ExpenseInstallment
from app.models.installment import STATUS_PAID
from app.services.expenses import (
    ExpenseError,
    ExpenseInput,
    create_expense,
    get_expense,
    restore_expense,
    soft_delete_expense,
    update_expense,
)

pytestmark = pytest.mark.asyncio


async def test_i_l1_creating_an_expense_writes_plan_and_audit_together(
    async_session, people, fixtures, count_rows
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )

    assert expense.public_id == "EXP-000001"
    assert expense.total_amount_minor == 300_000
    assert len(expense.installments) == 3
    assert sum(line.amount_minor for line in expense.installments) == 300_000
    assert [line.statement_date for line in expense.installments] == [
        date(2026, 9, 10),
        date(2026, 10, 10),
        date(2026, 11, 10),
    ]
    assert await count_rows(AuditLog) == 1


async def test_i_l2_a_failure_after_the_insert_leaves_nothing_behind(
    async_session, people, fixtures, count_rows, monkeypatch
):
    """Harcama satiri yazildiktan sonra patlarsa hicbir sey kalmamalidir.

    Hata bilerek `record_audit` icine yerlestirilir: bu nokta flush'tan
    sonradir, yani harcama ve taksit satirlari transaction icinde zaten
    yazilmistir. Geri alma calismazsa yarim veri kalirdi.
    """
    import app.services.expenses as service

    def explode(*_args, **_kwargs):
        raise RuntimeError("denetim kaydi yazilamadi")

    monkeypatch.setattr(service, "record_audit", explode)

    with pytest.raises(RuntimeError):
        await create_expense(
            async_session,
            user=people["aykut"],
            data=ExpenseInput(
                payment_method_id=fixtures["card"].id,
                category_id=fixtures["category"].id,
                transaction_date=date(2026, 9, 8),
                amount="3.000",
                installment_count=3,
            ),
        )

    assert await count_rows(Expense) == 0
    assert await count_rows(ExpenseInstallment) == 0
    assert await count_rows(AuditLog) == 0


@pytest.mark.parametrize(
    "changes, expected_first_statement",
    [
        ({"amount": "6.000"}, date(2026, 9, 10)),
        ({"transaction_date": date(2026, 9, 11)}, date(2026, 10, 10)),
        ({"installment_count": 6}, date(2026, 9, 10)),
    ],
)
async def test_i_l3_l6_financial_changes_regenerate_the_plan(
    async_session, people, fixtures, changes, expected_first_statement
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )

    updated = await update_expense(
        async_session, user=people["aykut"], expense=expense, changes=changes
    )

    assert len(updated.installments) == updated.installment_count
    assert sum(l.amount_minor for l in updated.installments) == updated.total_amount_minor
    assert updated.installments[0].statement_date == expected_first_statement


async def test_i_l5_changing_the_card_refreshes_the_snapshot(
    async_session, people, fixtures
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )

    updated = await update_expense(
        async_session,
        user=people["aykut"],
        expense=expense,
        changes={"payment_method_id": fixtures["other_card"].id},
    )

    assert updated.statement_day_snapshot == 25
    assert updated.due_offset_days_snapshot == 10
    assert updated.installments[0].statement_date == date(2026, 9, 25)
    assert updated.installments[0].due_date == date(2026, 10, 5)


@pytest.mark.parametrize(
    "changes", [{"description": "Migros alışverişi"}, {"category_id": 2}]
)
async def test_i_l7_l8_non_financial_changes_leave_the_plan_untouched(
    async_session, people, fixtures, changes
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )
    before = [
        (line.installment_number, line.amount_minor, line.statement_date, line.due_date)
        for line in expense.installments
    ]

    updated = await update_expense(
        async_session, user=people["aykut"], expense=expense, changes=changes
    )

    after = [
        (line.installment_number, line.amount_minor, line.statement_date, line.due_date)
        for line in updated.installments
    ]
    assert after == before


async def test_i_l9_changing_the_card_settings_does_not_move_past_installments(
    async_session, people, fixtures
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )
    before = [
        (line.amount_minor, line.statement_date, line.due_date)
        for line in expense.installments
    ]

    # Kart kosullari tamamen degistirilir.
    fixtures["card"].statement_day = 1
    await async_session.commit()

    reloaded = await get_expense(async_session, expense.id)
    after = [
        (line.amount_minor, line.statement_date, line.due_date)
        for line in reloaded.installments
    ]
    assert after == before
    assert reloaded.statement_day_snapshot == 10


async def test_i_l10_soft_delete_keeps_rows_and_records_an_audit_entry(
    async_session, people, fixtures, count_rows
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )

    await soft_delete_expense(async_session, user=people["aykut"], expense=expense)

    assert expense.deleted_at is not None
    assert await count_rows(ExpenseInstallment) == 3
    assert await get_expense(async_session, expense.id) is None
    assert await get_expense(async_session, expense.id, include_deleted=True) is not None
    assert await count_rows(AuditLog) == 2

    await restore_expense(async_session, user=people["aykut"], expense=expense)
    assert await get_expense(async_session, expense.id) is not None


async def test_i_l11_public_ids_are_sequential_and_unique(
    async_session, people, fixtures
):
    public_ids = []
    for _ in range(3):
        expense = await create_expense(
            async_session,
            user=people["aykut"],
            data=ExpenseInput(
                payment_method_id=fixtures["cash"].id,
                category_id=fixtures["category"].id,
                transaction_date=date(2026, 9, 8),
                amount="50",
            ),
        )
        public_ids.append(expense.public_id)

    assert public_ids == ["EXP-000001", "EXP-000002", "EXP-000003"]


async def test_i_l12_paid_installments_block_financial_edits(
    async_session, people, fixtures
):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="3.000",
            installment_count=3,
        ),
    )
    expense.installments[0].status = STATUS_PAID
    await async_session.commit()

    with pytest.raises(ExpenseError):
        await update_expense(
            async_session, user=people["aykut"], expense=expense, changes={"amount": "9.000"}
        )

    # Aciklama degisikligi hala serbesttir.
    updated = await update_expense(
        async_session,
        user=people["aykut"],
        expense=expense,
        changes={"description": "ödenmiş"},
    )
    assert updated.description == "ödenmiş"


async def test_cash_expense_cannot_be_split_into_installments(
    async_session, people, fixtures
):
    with pytest.raises(ExpenseError):
        await create_expense(
            async_session,
            user=people["aykut"],
            data=ExpenseInput(
                payment_method_id=fixtures["cash"].id,
                category_id=fixtures["category"].id,
                transaction_date=date(2026, 9, 8),
                amount="500",
                installment_count=3,
            ),
        )


async def test_inactive_payment_method_is_refused(async_session, people, fixtures):
    fixtures["card"].is_active = False
    await async_session.commit()

    with pytest.raises(ExpenseError):
        await create_expense(
            async_session,
            user=people["aykut"],
            data=ExpenseInput(
                payment_method_id=fixtures["card"].id,
                category_id=fixtures["category"].id,
                transaction_date=date(2026, 9, 8),
                amount="500",
            ),
        )


async def test_unknown_field_cannot_be_edited(async_session, people, fixtures):
    expense = await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["cash"].id,
            category_id=fixtures["category"].id,
            transaction_date=date(2026, 9, 8),
            amount="500",
        ),
    )

    with pytest.raises(ExpenseError):
        await update_expense(
            async_session,
            user=people["aykut"],
            expense=expense,
            changes={"created_by_user_id": 999},
        )


async def test_audit_entry_never_stores_credentials(async_session, people, fixtures):
    from app.services.audit import _serialise

    payload = _serialise({"amount": 100, "bot_token": "gizli", "init_data": "xyz"})
    assert "gizli" not in payload
    assert "xyz" not in payload
    assert "amount" in payload
