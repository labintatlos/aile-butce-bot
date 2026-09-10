"""store receipt photos

Fiş fotoğrafları artık Telegram'da değil, veri dizininde saklanır; harcamada
dosyanın adı tutulur. Eski `receipt_file_id` sütunu, Telegram'dan henüz
aktarılmamış fişleri kaybetmemek için yerinde bırakılır.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expenses", sa.Column("receipt_path", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("receipt_path")
