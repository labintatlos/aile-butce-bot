"""add shared flag

Ortak ve kişisel harcamanın ayrılması, iki kişilik bir kurulumda "kim kime ne
kadar borçlu" sorusunun yanıtlanabilmesi içindir. Varsayılan ortaktır: mevcut
kayıtların tamamı ortak sayılır, çünkü bugüne kadar böyle giriliyorlardı.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column(
            "is_shared", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("is_shared")
