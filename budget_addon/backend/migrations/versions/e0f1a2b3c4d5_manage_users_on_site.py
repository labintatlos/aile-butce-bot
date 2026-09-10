"""manage users on site

Kişiler artık Telegram kimliğine bağlı değildir: sitedeki yönetici ekranından
eklenir, şifreleri orada belirlenir. Bu yüzden `telegram_user_id` boş
bırakılabilir hâle gelir ve kimin kişileri yönetebileceğini söyleyen
`is_admin` alanı eklenir.

Önceden web girişi tanımlanmış kişiler yönetici sayılır: bugüne kadar
girişleri eklenti ayarlarından yöneten onlardı. Hiç web girişi yoksa site
ilk açılışta kurulum ekranını gösterir.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "telegram_user_id", existing_type=sa.BigInteger(), nullable=True
        )
        batch.add_column(
            sa.Column(
                "is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")
            )
        )
    op.execute(
        "UPDATE users SET is_admin = 1 "
        "WHERE username IS NOT NULL AND password_hash IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")
        batch.alter_column(
            "telegram_user_id", existing_type=sa.BigInteger(), nullable=False
        )
