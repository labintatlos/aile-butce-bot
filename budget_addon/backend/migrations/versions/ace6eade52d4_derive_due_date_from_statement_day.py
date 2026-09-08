"""derive due date from statement day

Kullanıcı artık yalnızca hesap kesim gününü girer. Son ödeme tarihi ekstre
tarihinden `due_offset_days` gün sonrasıdır ve hafta sonuna denk gelirse
pazartesiye taşınır.

SQLite sütun silmeyi desteklemediği için Alembic tabloyu yeniden oluşturur ve
bunu yaparken mevcut CHECK kısıtlarını olduğu gibi kopyalar. Eski kısıtlar
kaldırılan `due_day` sütununa atıfta bulunduğu için otomatik üretilen göç
"no such column: due_day" hatası veriyordu. Bu yüzden hedef tablo `copy_from`
ile açıkça tanımlanır; böylece Alembic yeni kısıt kümesini kullanır.

Revision ID: ace6eade52d4
Revises: e14c14326370
Create Date: 2026-09-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "ace6eade52d4"
down_revision: str | None = "e14c14326370"
branch_labels = None
depends_on = None


def _payment_methods_table(*, with_due_day: bool) -> sa.Table:
    """Tablonun yeniden oluşturulacak hâli.

    `with_due_day` geriye alma yönü içindir.
    """
    columns = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("statement_day", sa.Integer(), nullable=True),
        sa.Column("cutoff_inclusive", sa.Boolean(), nullable=False),
        sa.Column("credit_limit_minor", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        # server_default burada tekrar yazilmak zorunda: SQLite tabloyu
        # yeniden olusturdugu icin atlanirsa varsayilan kaybolur ve her ekleme
        # "NOT NULL constraint failed: created_at" ile duser.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    ]
    if with_due_day:
        columns.insert(6, sa.Column("due_day", sa.Integer(), nullable=True))
        day_constraints = [
            sa.CheckConstraint(
                "type <> 'cash' OR (statement_day IS NULL AND due_day IS NULL)",
                name="ck_cash_has_no_statement_days",
            ),
            sa.CheckConstraint(
                "type <> 'credit_card' OR (statement_day IS NOT NULL AND "
                "due_day IS NOT NULL AND statement_day BETWEEN 1 AND 31 AND "
                "due_day BETWEEN 1 AND 31)",
                name="ck_credit_card_days_in_range",
            ),
        ]
    else:
        columns.insert(
            6,
            sa.Column(
                "due_offset_days", sa.Integer(), nullable=False, server_default="10"
            ),
        )
        day_constraints = [
            sa.CheckConstraint(
                "type <> 'cash' OR statement_day IS NULL",
                name="ck_cash_has_no_statement_days",
            ),
            sa.CheckConstraint(
                "type <> 'credit_card' OR (statement_day IS NOT NULL AND "
                "statement_day BETWEEN 1 AND 31)",
                name="ck_credit_card_days_in_range",
            ),
            sa.CheckConstraint(
                "due_offset_days BETWEEN 1 AND 60", name="ck_due_offset_in_range"
            ),
        ]

    return sa.Table(
        "payment_methods",
        sa.MetaData(),
        *columns,
        sa.CheckConstraint(
            "type IN ('cash', 'credit_card')", name="ck_payment_method_type"
        ),
        *day_constraints,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("name"),
    )


def upgrade() -> None:
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("due_offset_days_snapshot", sa.Integer(), nullable=True)
        )
        batch_op.drop_column("due_day_snapshot")

    with op.batch_alter_table(
        "payment_methods",
        schema=None,
        copy_from=_payment_methods_table(with_due_day=True),
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "due_offset_days", sa.Integer(), nullable=False, server_default="10"
            )
        )
        batch_op.drop_column("due_day")
        batch_op.drop_constraint("ck_cash_has_no_statement_days", type_="check")
        batch_op.drop_constraint("ck_credit_card_days_in_range", type_="check")
        batch_op.create_check_constraint(
            "ck_cash_has_no_statement_days", "type <> 'cash' OR statement_day IS NULL"
        )
        batch_op.create_check_constraint(
            "ck_credit_card_days_in_range",
            "type <> 'credit_card' OR (statement_day IS NOT NULL AND "
            "statement_day BETWEEN 1 AND 31)",
        )
        batch_op.create_check_constraint(
            "ck_due_offset_in_range", "due_offset_days BETWEEN 1 AND 60"
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "payment_methods",
        schema=None,
        copy_from=_payment_methods_table(with_due_day=False),
    ) as batch_op:
        batch_op.add_column(sa.Column("due_day", sa.Integer(), nullable=True))
        batch_op.drop_column("due_offset_days")
        batch_op.drop_constraint("ck_due_offset_in_range", type_="check")

    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("due_day_snapshot", sa.Integer(), nullable=True))
        batch_op.drop_column("due_offset_days_snapshot")
