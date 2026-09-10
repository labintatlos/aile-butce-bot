"""add receipt photos

Fiş fotoğrafı Telegram dosya kimliği olarak saklanır; dosyanın kendisi
eklentide tutulmaz. Kimlik aynı bot için kalıcı olduğundan fiş, sohbetin
içinde yeniden gösterilebilir.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expenses", sa.Column("receipt_file_id", sa.String(length=256), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("receipt_file_id")
