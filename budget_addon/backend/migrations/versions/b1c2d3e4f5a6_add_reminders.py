"""add reminders

Zamanlanmış hatırlatmalar için iki ekleme yapılır:

- `users.reminders_enabled`: kullanıcı hatırlatmaları kapatabilsin diye.
  Varsayılanı açıktır; mevcut kayıtlar da açık olarak işaretlenir.
- `notification_log`: gönderilmiş her hatırlatmanın kaydı. Eklenti yeniden
  başladığında aynı hatırlatmanın tekrar gönderilmesini bu tablo engeller.

Revision ID: b1c2d3e4f5a6
Revises: ace6eade52d4
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "ace6eade52d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        # server_default zorunludur: sutun NOT NULL ve tabloda zaten satirlar var.
        sa.Column(
            "reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=96), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "reference", name="uq_notification_kind_reference"),
    )
    op.create_index(
        "ix_notification_log_kind", "notification_log", ["kind"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_notification_log_kind", table_name="notification_log")
    op.drop_table("notification_log")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("reminders_enabled")
