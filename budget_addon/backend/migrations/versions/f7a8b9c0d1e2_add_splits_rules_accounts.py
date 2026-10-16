"""add splits, rules, reconciliation, accounts, category groups and rollover

Bölünmüş harcama parçaları, otomatik kurallar, ekstre mutabakatı, hesaplar
ve hesap hareketleri; kategorilere grup ve devreden bütçe; taksit satırlarına
mutabakat işareti.

Mevcut tablolara yalnızca sütun eklenir (`ALTER TABLE ... ADD COLUMN`);
hiçbir tablo yeniden oluşturulmaz, bu yüzden mevcut kısıtlar ve veriler
olduğu gibi kalır.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.add_column("categories", sa.Column("group_name", sa.String(64), nullable=True))
    op.add_column(
        "categories",
        sa.Column("rollover", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("categories", sa.Column("rollover_since", sa.Date(), nullable=True))
    op.add_column(
        "expense_installments",
        sa.Column("cleared", sa.Boolean(), nullable=False, server_default="0"),
    )

    op.create_table(
        "expense_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "expense_id",
            sa.Integer(),
            sa.ForeignKey("expenses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("amount_minor > 0", name="ck_expense_split_amount_positive"),
    )
    op.create_index("ix_expense_splits_expense_id", "expense_splits", ["expense_id"])
    op.create_index("ix_expense_splits_category_id", "expense_splits", ["category_id"])

    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.String(120), nullable=False),
        sa.Column("match_type", sa.String(16), nullable=False, server_default="contains"),
        sa.Column(
            "set_category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "set_payment_method_id",
            sa.Integer(),
            sa.ForeignKey("payment_methods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("set_description", sa.String(120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "match_type IN ('contains', 'equals', 'starts_with')",
            name="ck_rule_match_type",
        ),
    )
    op.create_index("ix_rules_set_category_id", "rules", ["set_category_id"])

    op.create_table(
        "statement_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "payment_method_id",
            sa.Integer(),
            sa.ForeignKey("payment_methods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.Column("bank_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("ours_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column(
            "reconciled_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "payment_method_id", "statement_date", name="uq_reconciliation_statement"
        ),
    )
    op.create_index(
        "ix_statement_reconciliations_payment_method_id",
        "statement_reconciliations",
        ["payment_method_id"],
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="bank"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.String(200), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('bank', 'cash', 'savings', 'investment', 'other')",
            name="ck_account_kind",
        ),
    )

    op.create_table(
        "account_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("transfer_group", sa.String(32), nullable=True),
        sa.Column("payment_method_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "kind IN ('balance', 'transfer', 'adjustment')", name="ck_account_entry_kind"
        ),
    )
    op.create_index("ix_account_entries_account_id", "account_entries", ["account_id"])
    op.create_index("ix_account_entries_entry_date", "account_entries", ["entry_date"])
    op.create_index(
        "ix_account_entries_transfer_group", "account_entries", ["transfer_group"]
    )


def downgrade() -> None:
    op.drop_index("ix_account_entries_transfer_group", table_name="account_entries")
    op.drop_index("ix_account_entries_entry_date", table_name="account_entries")
    op.drop_index("ix_account_entries_account_id", table_name="account_entries")
    op.drop_table("account_entries")
    op.drop_table("accounts")
    op.drop_index(
        "ix_statement_reconciliations_payment_method_id",
        table_name="statement_reconciliations",
    )
    op.drop_table("statement_reconciliations")
    op.drop_index("ix_rules_set_category_id", table_name="rules")
    op.drop_table("rules")
    op.drop_index("ix_expense_splits_category_id", table_name="expense_splits")
    op.drop_index("ix_expense_splits_expense_id", table_name="expense_splits")
    op.drop_table("expense_splits")
    with op.batch_alter_table("expense_installments") as batch:
        batch.drop_column("cleared")
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("rollover_since")
        batch.drop_column("rollover")
        batch.drop_column("group_name")
