"""add refunds

İade, harcamanın silinmesi değil ona bağlı ayrı bir alacak kaydıdır: alışveriş
gerçekten oldu, taksitleri ekstreye girdi ve kısmi iade silmeyle
anlatılamazdı.

`statement_date` ve `due_date` kayıt anında hesaplanıp saklanır; harcamanın
anlık görüntü ilkesiyle aynı gerekçeyle, kart ayarı sonradan değişse bile
yeniden hesaplanmaz.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expense_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("refund_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("amount_minor > 0", name="ck_refund_amount_positive"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("expense_id", "created_by_user_id", "refund_date",
                   "statement_date", "due_date", "category_id", "deleted_at"):
        op.create_index(f"ix_refunds_{column}", "refunds", [column])


def downgrade() -> None:
    for column in ("deleted_at", "category_id", "due_date", "statement_date",
                   "refund_date", "created_by_user_id", "expense_id"):
        op.drop_index(f"ix_refunds_{column}", table_name="refunds")
    op.drop_table("refunds")
