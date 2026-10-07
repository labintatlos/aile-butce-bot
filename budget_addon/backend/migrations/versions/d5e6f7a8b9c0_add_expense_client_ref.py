"""add expense client ref

Çevrimdışı girilen hızlı harcamalar telefon bağlantı bulunca gönderilir.
Sunucunun yanıtı yolda kaybolursa telefon aynı kaydı yeniden gönderir; her
kayda telefonda verilen tekil anahtar (`client_ref`) ikinci gönderimin yeni bir
harcama açmasını engeller.

SQLite mevcut tabloya UNIQUE sütun ekleyemez; tekillik bir benzersiz indeksle
sağlanır. Boş değerler (sitede formdan girilen kayıtlar) indekste çakışmaz.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("client_ref", sa.String(64), nullable=True))
    op.create_index("ix_expenses_client_ref", "expenses", ["client_ref"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_expenses_client_ref", table_name="expenses")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_column("client_ref")
