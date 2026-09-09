"""add category budgets

Kategori başına aylık hedef. Boş bırakılabilir; hedefi olmayan kategori uyarı
üretmez. Hedef harcamayı engellemez, yalnızca aşıldığında haber verilmesini
sağlar.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("monthly_budget_minor", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("monthly_budget_minor")
