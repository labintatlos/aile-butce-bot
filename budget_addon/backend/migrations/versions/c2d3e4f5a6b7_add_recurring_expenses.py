"""add recurring expenses

Sabit giderler (kira, aidat, abonelik) bir şablon tablosunda tutulur ve her ay
gerçek bir harcamaya dönüştürülür. Üretilen harcama, hangi şablondan geldiğini
`expenses.recurring_expense_id` ile taşır; aynı ay içinde ikinci kez üretim bu
bağ sorgulanarak engellenir.

Sütun SQLite'ta `ALTER TABLE ... ADD COLUMN` ile eklenir ve yabancı anahtar
kısıtı taşımaz: SQLite mevcut bir tabloya kısıt ekleyemez, tabloyu yalnızca
bunun için yeniden oluşturmak ise `expenses` üzerindeki CHECK kısıtlarını
riske atardı. Bağın tutarlılığı uygulama tarafında sağlanır.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("payment_method_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("amount_minor > 0", name="ck_recurring_amount_positive"),
        sa.CheckConstraint(
            "day_of_month BETWEEN 1 AND 31", name="ck_recurring_day_in_range"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id"], ["payment_methods.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recurring_expenses_created_by_user_id",
        "recurring_expenses",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_recurring_expenses_payment_method_id",
        "recurring_expenses",
        ["payment_method_id"],
    )
    op.create_index(
        "ix_recurring_expenses_category_id", "recurring_expenses", ["category_id"]
    )

    op.add_column(
        "expenses",
        # SQLite mevcut tabloya kisit ekleyemez; bag uygulama tarafinda
        # yonetilir (bkz. models/expense.py aciklamasi).
        sa.Column("recurring_expense_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_expenses_recurring_expense_id", "expenses", ["recurring_expense_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_expenses_recurring_expense_id", table_name="expenses")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("recurring_expense_id")
    op.drop_index("ix_recurring_expenses_category_id", table_name="recurring_expenses")
    op.drop_index(
        "ix_recurring_expenses_payment_method_id", table_name="recurring_expenses"
    )
    op.drop_index(
        "ix_recurring_expenses_created_by_user_id", table_name="recurring_expenses"
    )
    op.drop_table("recurring_expenses")
