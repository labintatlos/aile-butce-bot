"""add incomes

Gelir kaydı olmadan "ay sonunda ne kalacak" sorusu yanıtlanamaz. Tablo
harcamalarla aynı ilkeleri izler: tutar kuruş cinsinden tam sayıdır ve silme
yumuşaktır.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount_minor > 0", name="ck_income_amount_positive"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incomes_created_by_user_id", "incomes", ["created_by_user_id"])
    op.create_index("ix_incomes_received_date", "incomes", ["received_date"])
    op.create_index("ix_incomes_deleted_at", "incomes", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_incomes_deleted_at", table_name="incomes")
    op.drop_index("ix_incomes_received_date", table_name="incomes")
    op.drop_index("ix_incomes_created_by_user_id", table_name="incomes")
    op.drop_table("incomes")
