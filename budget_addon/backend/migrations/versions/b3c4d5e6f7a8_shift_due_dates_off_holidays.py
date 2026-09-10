"""shift due dates off public holidays

Son ödeme tarihleri artık resmî tatilleri de atlıyor. Taksitlerin son ödeme
tarihi saklandığı için, günü henüz gelmemiş ve tatile denk gelen kayıtlar ilk
iş gününe taşınır. Eski kural hafta sonunu zaten atladığından, saklanan
tarihten ileri doğru ilk iş gününü aramak yeni kuralla aynı sonucu verir.
Geçmiş tarihlere dokunulmaz.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-10
"""

from __future__ import annotations

from datetime import date, timedelta

import holidays
import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

installments = sa.table(
    "expense_installments",
    sa.column("id", sa.Integer),
    sa.column("due_date", sa.Date),
)


def _next_business_day(value: date, calendar: holidays.HolidayBase) -> date:
    while value.weekday() >= 5 or value in calendar:
        value += timedelta(days=1)
    return value


def upgrade() -> None:
    bind = op.get_bind()
    calendar = holidays.country_holidays("TR")
    rows = bind.execute(
        sa.select(installments.c.id, installments.c.due_date).where(
            installments.c.due_date >= date.today()
        )
    ).all()
    for row_id, due in rows:
        shifted = _next_business_day(due, calendar)
        if shifted != due:
            bind.execute(
                installments.update()
                .where(installments.c.id == row_id)
                .values(due_date=shifted)
            )


def downgrade() -> None:
    # Taşınan tarihler eski kurala göre de geçerli iş günleridir; geri almaya
    # gerek yok.
    pass
