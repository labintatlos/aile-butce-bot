"""add personal budgets

Harcamaya kime ait olduğu (`owner_user_id`) eklenir ve kişi başı yıllık
kişisel bütçe tablosu oluşturulur. Daha önce kişisel işaretlenmiş harcamaların
sahibi, kaydı giren kişi kabul edilir.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_expenses_owner_user_id", "expenses", ["owner_user_id"])
    op.execute(
        "UPDATE expenses SET owner_user_id = created_by_user_id WHERE is_shared = 0"
    )

    op.create_table(
        "personal_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("user_id", "year", name="uq_personal_budget_user_year"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_personal_budget_amount"),
    )
    op.create_index("ix_personal_budgets_user_id", "personal_budgets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_personal_budgets_user_id", table_name="personal_budgets")
    op.drop_table("personal_budgets")
    op.drop_index("ix_expenses_owner_user_id", table_name="expenses")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("owner_user_id")
