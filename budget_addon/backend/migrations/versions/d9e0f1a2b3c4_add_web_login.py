"""add web login

Web sitesine kullanıcı adı ve şifreyle giriş için. İki alan da boş
bırakılabilir: web girişi tanımlanmamış kullanıcı yalnızca Telegram ve Home
Assistant paneli üzerinden erişmeye devam eder. Parola düz metin olarak değil,
yalnızca scrypt özeti olarak saklanır.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_hash")
        batch.drop_column("username")
