"""add savings goals

Birikim hedefleri: ad, hedef tutar, hedef tarih ve biriken tutar.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("target_minor", sa.BigInteger(), nullable=False),
        sa.Column("saved_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("target_minor > 0", name="ck_savings_goal_target_positive"),
        sa.CheckConstraint("saved_minor >= 0", name="ck_savings_goal_saved_not_negative"),
    )
    op.create_index(
        "ix_savings_goals_created_by_user_id", "savings_goals", ["created_by_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_savings_goals_created_by_user_id", table_name="savings_goals")
    op.drop_table("savings_goals")
