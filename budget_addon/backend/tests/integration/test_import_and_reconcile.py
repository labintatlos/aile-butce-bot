"""Ekstre içe aktarma ve ekstre mutabakatı."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import Expense
from app.services import importer, reconcile
from app.services import rules as rules_service
from app.services.expenses import ExpenseInput, create_expense
from app.services.refunds import create_refund

pytestmark = pytest.mark.asyncio

CARD_STATEMENT = """Kart Ekstresi;;
İşlem Tarihi;Açıklama;Tutar
01.10.2026;MIGROS ISTANBUL;1.250,40
02.10.2026;SHELL BENZIN;2.000,00
03.10.2026;TEKNOSA 1/3;1.000,00
04.10.2026;VATAN 2/6;500,00
05.10.2026;ODEME - TESEKKURLER;-5.000,00
06.10.2026;KAFE;0,00
"""


async def _preview(session, fixtures, text=CARD_STATEMENT, **extra):
    return await importer.preview(
        session,
        text=text,
        payment_method_id=fixtures["card"].id,
        default_category_id=fixtures["category"].id,
        **extra,
    )


async def test_the_preview_reads_a_card_statement(async_session, people, fixtures):
    result = await _preview(async_session, fixtures)

    assert result.sign == importer.SIGN_POSITIVE
    rows = {row.description: row for row in result.rows}
    assert rows["MIGROS ISTANBUL"].amount_minor == 125_040
    assert rows["MIGROS ISTANBUL"].selected
    assert rows["ODEME - TESEKKURLER"].skip_reason == importer.SKIP_OPPOSITE
    assert rows["KAFE"].skip_reason == importer.SKIP_ZERO


async def test_installment_lines_are_flagged(async_session, people, fixtures):
    rows = {row.description: row for row in (await _preview(async_session, fixtures)).rows}

    first = rows["TEKNOSA 1/3"]
    assert (first.installment_count, first.amount_minor, first.selected) == (3, 300_000, True)
    later = rows["VATAN 2/6"]
    assert later.installment_current == 2
    assert not later.selected


async def test_already_recorded_expenses_are_not_selected_again(async_session, people, fixtures):
    await create_expense(
        async_session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["fuel"].id,
            transaction_date=date(2026, 10, 3),
            amount="2.000",
            description="benzin",
        ),
    )
    rows = {row.description: row for row in (await _preview(async_session, fixtures)).rows}

    assert rows["SHELL BENZIN"].duplicate_of == "EXP-000001"
    assert not rows["SHELL BENZIN"].selected
    assert rows["MIGROS ISTANBUL"].duplicate_of is None


async def test_rules_fill_the_category_and_rename(async_session, people, fixtures):
    await rules_service.create_rule(
        async_session,
        user=people["aykut"],
        values={
            "pattern": "shell",
            "set_category_id": fixtures["fuel"].id,
            "set_description": "Shell",
        },
    )
    rows = {row.index: row for row in (await _preview(async_session, fixtures)).rows}
    shell = rows[3]

    assert shell.description == "Shell"
    assert shell.category_id == fixtures["fuel"].id
    assert shell.category_source == "rule"
    assert rows[2].category_source == "default"


async def test_account_statements_with_negative_spending_are_understood(
    async_session, people, fixtures
):
    text = "Tarih,Açıklama,Tutar\n01.10.2026,Market,-150.25\n02.10.2026,Maaş,30000.00\n03.10.2026,Eczane,-80.00\n"
    result = await _preview(async_session, fixtures, text=text)

    assert result.sign == importer.SIGN_NEGATIVE
    selected = [row.description for row in result.rows if row.selected]
    assert selected == ["Market", "Eczane"]


async def test_selected_rows_are_saved_in_one_transaction(async_session, people, fixtures):
    rows = [
        importer.ImportRow(
            transaction_date=date(2026, 10, 1),
            description="MIGROS",
            amount_minor=125_040,
            category_id=fixtures["category"].id,
            payment_method_id=fixtures["card"].id,
        ),
        importer.ImportRow(
            transaction_date=date(2026, 10, 3),
            description="TEKNOSA",
            amount_minor=300_000,
            category_id=fixtures["category"].id,
            payment_method_id=fixtures["card"].id,
            installment_count=3,
        ),
    ]
    created = await importer.commit_rows(async_session, user=people["aykut"], rows=rows)
    assert [expense.installment_count for expense in created] == [1, 3]

    broken = [
        rows[0],
        importer.ImportRow(
            transaction_date=date(2026, 10, 3),
            description="nakitte taksit olmaz",
            amount_minor=10_000,
            category_id=fixtures["category"].id,
            payment_method_id=fixtures["cash"].id,
            installment_count=3,
        ),
    ]
    with pytest.raises(importer.ImportFileError, match="2. satır"):
        await importer.commit_rows(async_session, user=people["aykut"], rows=broken)
    count = await async_session.scalar(select(func.count(Expense.id)))
    assert count == 2


# ---------------------------------------------------------------------------
# Mutabakat
# ---------------------------------------------------------------------------


async def _card_expense(session, people, fixtures, when, amount, installments=1):
    return await create_expense(
        session,
        user=people["aykut"],
        data=ExpenseInput(
            payment_method_id=fixtures["card"].id,
            category_id=fixtures["category"].id,
            transaction_date=when,
            amount=amount,
            installment_count=installments,
        ),
    )


async def test_the_statement_total_is_compared_with_the_bank(async_session, people, fixtures):
    # Kesim gunu 10: 5 Ekim'deki harcamalar 10 Ekim ekstresine duser.
    first = await _card_expense(async_session, people, fixtures, date(2026, 10, 5), "1.000")
    await _card_expense(async_session, people, fixtures, date(2026, 10, 6), "300")
    await create_refund(
        async_session,
        user=people["aykut"],
        expense_id=first.id,
        amount=10_000,
        refund_date=date(2026, 10, 7),
    )

    statement = date(2026, 10, 10)
    detail = await reconcile.detail(
        async_session, payment_method_id=fixtures["card"].id, statement_date=statement
    )
    assert detail.summary.ours_total_minor == 120_000
    assert [line.kind for line in detail.lines] == ["installment", "installment", "refund"]

    saved = await reconcile.save(
        async_session,
        user=people["aykut"],
        payment_method_id=fixtures["card"].id,
        statement_date=statement,
        bank_total_minor=125_000,
        note="kafe eksik",
    )
    assert saved.summary.difference_minor == 5_000
    assert not saved.summary.is_reconciled

    await _card_expense(async_session, people, fixtures, date(2026, 10, 8), "50")
    listed = await reconcile.statements(
        async_session, payment_method_id=fixtures["card"].id, today=date(2026, 10, 16)
    )
    current = next(item for item in listed if item.statement_date == statement)
    assert current.is_reconciled
    assert current.changed_since


async def test_lines_can_be_ticked_off(async_session, people, fixtures):
    await _card_expense(async_session, people, fixtures, date(2026, 10, 5), "1.000")
    statement = date(2026, 10, 10)
    detail = await reconcile.detail(
        async_session, payment_method_id=fixtures["card"].id, statement_date=statement
    )
    line_ids = [line.id for line in detail.lines]

    changed = await reconcile.set_cleared(
        async_session, payment_method_id=fixtures["card"].id, installment_ids=line_ids, cleared=True
    )
    assert changed == 1
    detail = await reconcile.detail(
        async_session, payment_method_id=fixtures["card"].id, statement_date=statement
    )
    assert detail.cleared_total_minor == 100_000

    # Baska bir kartin satiri bu kartin uzerinden isaretlenemez.
    assert (
        await reconcile.set_cleared(
            async_session,
            payment_method_id=fixtures["other_card"].id,
            installment_ids=line_ids,
            cleared=False,
        )
        == 0
    )


async def test_cash_cannot_be_reconciled(async_session, people, fixtures):
    with pytest.raises(reconcile.ReconcileError):
        await reconcile.statements(
            async_session, payment_method_id=fixtures["cash"].id, today=date(2026, 10, 16)
        )
