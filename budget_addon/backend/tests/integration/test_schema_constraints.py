"""Veritabanı kısıtlarının kötü veriyi gerçekten reddettiğini doğrular.

Bu testler uygulama katmanını atlayıp doğrudan veritabanına yazar. Amaç,
serviste bir hata olsa bile şemanın son savunma hattı olarak durduğunu
göstermektir.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Category, Expense, ExpenseInstallment, PaymentMethod, User
from app.models.expense import format_public_id
from app.models.payment_method import TYPE_CASH, TYPE_CREDIT_CARD


@pytest.fixture()
def fixtures(session):
    user = User(telegram_user_id=111, display_name="Aykut", role="owner")
    category = Category(name="Market", emoji="🛒")
    card = PaymentMethod(
        name="Aslıhan Kredi Kartı 1",
        type=TYPE_CREDIT_CARD,
        statement_day=10,
        due_day=20,
    )
    session.add_all([user, category, card])
    session.commit()
    return {"user": user, "category": category, "card": card}


def make_expense(fixtures, **overrides):
    card = fixtures["card"]
    values = dict(
        public_id=format_public_id(1),
        created_by_user_id=fixtures["user"].id,
        payment_method_id=card.id,
        category_id=fixtures["category"].id,
        transaction_date=date(2026, 9, 8),
        total_amount_minor=300_000,
        installment_count=3,
        payment_method_type_snapshot=card.type,
        payment_method_name_snapshot=card.name,
        statement_day_snapshot=card.statement_day,
        due_day_snapshot=card.due_day,
        cutoff_inclusive_snapshot=card.cutoff_inclusive,
    )
    values.update(overrides)
    return Expense(**values)


def test_cash_method_cannot_carry_statement_days(session):
    session.add(PaymentMethod(name="Nakit", type=TYPE_CASH, statement_day=10))
    with pytest.raises(IntegrityError):
        session.commit()


def test_credit_card_days_must_be_within_range(session):
    session.add(
        PaymentMethod(name="Bozuk Kart", type=TYPE_CREDIT_CARD, statement_day=32, due_day=20)
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_credit_card_requires_both_days(session):
    session.add(PaymentMethod(name="Yarim Kart", type=TYPE_CREDIT_CARD, statement_day=10))
    with pytest.raises(IntegrityError):
        session.commit()


def test_unknown_payment_method_type_is_rejected(session):
    session.add(PaymentMethod(name="Kripto", type="bitcoin"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_expense_amount_must_be_positive(session, fixtures):
    session.add(make_expense(fixtures, total_amount_minor=0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_expense_installment_count_is_capped_at_twelve(session, fixtures):
    session.add(make_expense(fixtures, installment_count=13))
    with pytest.raises(IntegrityError):
        session.commit()


def test_installment_number_cannot_exceed_its_count(session, fixtures):
    session.add(make_expense(fixtures))
    session.commit()
    session.add(
        ExpenseInstallment(
            expense_id=1,
            installment_number=4,
            installment_count=3,
            amount_minor=100_000,
            statement_date=date(2026, 9, 10),
            due_date=date(2026, 9, 20),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_installment_numbers_are_unique_per_expense(session, fixtures):
    session.add(make_expense(fixtures))
    session.commit()
    for _ in range(2):
        session.add(
            ExpenseInstallment(
                expense_id=1,
                installment_number=1,
                installment_count=3,
                amount_minor=100_000,
                statement_date=date(2026, 9, 10),
                due_date=date(2026, 9, 20),
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()


def test_unknown_installment_status_is_rejected(session, fixtures):
    session.add(make_expense(fixtures))
    session.commit()
    session.add(
        ExpenseInstallment(
            expense_id=1,
            installment_number=1,
            installment_count=3,
            amount_minor=100_000,
            statement_date=date(2026, 9, 10),
            due_date=date(2026, 9, 20),
            status="belki",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_expense_cannot_reference_a_missing_category(session, fixtures):
    session.add(make_expense(fixtures, category_id=9999))
    with pytest.raises(IntegrityError):
        session.commit()


def test_telegram_user_id_is_unique(session):
    session.add_all(
        [
            User(telegram_user_id=555, display_name="Aykut"),
            User(telegram_user_id=555, display_name="Aslıhan"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_an_expense_removes_its_installments(session, fixtures):
    expense = make_expense(fixtures)
    expense.installments.append(
        ExpenseInstallment(
            installment_number=1,
            installment_count=3,
            amount_minor=100_000,
            statement_date=date(2026, 9, 10),
            due_date=date(2026, 9, 20),
        )
    )
    session.add(expense)
    session.commit()
    assert session.query(ExpenseInstallment).count() == 1

    session.delete(expense)
    session.commit()
    assert session.query(ExpenseInstallment).count() == 0


def test_public_id_format():
    assert format_public_id(184) == "EXP-000184"
    assert format_public_id(1) == "EXP-000001"
