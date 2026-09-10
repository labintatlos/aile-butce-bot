"""add expense tags

Etiket, kategoriden farklı bir soruyu yanıtlar: "Bodrum tatili toplam ne
tuttu?" Aynı olayın harcamaları farklı kategorilerde olabilir.

Etiketler açıklamadaki `#tatil` sözcüklerinden çıkarılır ve harcamayla aynı
transaction içinde yazılır.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expense_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expense_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("expense_id", "tag", name="uq_expense_tag"),
    )
    op.create_index("ix_expense_tags_expense_id", "expense_tags", ["expense_id"])
    op.create_index("ix_expense_tags_tag", "expense_tags", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_expense_tags_tag", table_name="expense_tags")
    op.drop_index("ix_expense_tags_expense_id", table_name="expense_tags")
    op.drop_table("expense_tags")
