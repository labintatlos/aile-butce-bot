"""Sabit giderler: şablonların yönetimi ve aylık kayıtların üretilmesi.

Kira, aidat, abonelik ve okul taksiti her ay aynı gün, aynı tutarla tekrar
eder. Bunları elle girmek unutulmaya açıktır ve unutulduğunda "gelecek 12
aylık yük" raporu gerçek yükün yalnızca kredi kartı tarafını gösterir.

Üretim, harcamayı doğrudan yazmaz: mevcut `expenses.create_expense` yolundan
geçer. Böylece kart anlık görüntüsü, ekstre tarihi ve denetim kaydı sabit
giderlerde de normal bir harcamayla birebir aynı kurallarla oluşur.

Aynı şablonun bir ay içinde iki kez kayıt üretmesi, üretilmiş harcamanın
`recurring_expense_id` bağı sorgulanarak engellenir. Bu bağ, kullanıcı üretilen
kaydı silse bile durur; silinmiş bir sabit gider ertesi gün yeniden
canlanmamalıdır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import ACTION_CREATE, ACTION_DELETE, ACTION_UPDATE
from ..models.expense import Expense
from ..models.recurring_expense import RecurringExpense
from ..models.user import User
from ..utils.time import month_bounds
from .audit import record_audit
from .expenses import ExpenseInput, create_expense
from .finance.dates import normalized_date, validate_day_of_month
from .finance.money import parse_amount_to_minor

ENTITY_RECURRING = "recurring_expense"

CATCH_UP_MONTHS = 1
"""Geriye dönük kaç ay taranacağı.

Eklenti birkaç gün kapalı kalıp ay sınırını atlamış olabilir. Bir aylık
geriye bakış, kapalı kaldığı süre boyunca kaçan sabit gideri yakalar; daha
geriye gitmek, kullanıcının bilerek sildiği eski kayıtları diriltme riskini
artırmadan bir fayda sağlamaz.
"""


class RecurringError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


@dataclass(frozen=True, slots=True)
class GeneratedExpense:
    """Bir şablondan üretilmiş harcama."""

    template_name: str
    expense: Expense


# ---------------------------------------------------------------------------
# Şablon yönetimi
# ---------------------------------------------------------------------------


async def list_templates(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[RecurringExpense]:
    statement = select(RecurringExpense).order_by(
        RecurringExpense.day_of_month, RecurringExpense.name
    )
    if not include_inactive:
        statement = statement.where(RecurringExpense.is_active.is_(True))
    return list((await session.scalars(statement)).all())


async def get_template(
    session: AsyncSession, template_id: int
) -> RecurringExpense | None:
    return await session.get(RecurringExpense, template_id)


def _snapshot(template: RecurringExpense) -> dict[str, object]:
    return {
        "name": template.name,
        "amount_minor": template.amount_minor,
        "day_of_month": template.day_of_month,
        "start_date": template.start_date,
        "category_id": template.category_id,
        "payment_method_id": template.payment_method_id,
        "is_active": template.is_active,
    }


async def create_template(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    category_id: int,
    payment_method_id: int,
    amount: str | int,
    day_of_month: int,
    start_date: date | None = None,
    notes: str | None = None,
) -> RecurringExpense:
    name = name.strip()
    if not name:
        raise RecurringError("Sabit giderin adı boş olamaz")
    validate_day_of_month(day_of_month)
    amount_minor = parse_amount_to_minor(amount)
    if amount_minor <= 0:
        raise RecurringError("Tutar sıfırdan büyük olmalıdır")

    template = RecurringExpense(
        name=name,
        created_by_user_id=user.id,
        category_id=category_id,
        payment_method_id=payment_method_id,
        amount_minor=amount_minor,
        day_of_month=day_of_month,
        start_date=start_date or date.today(),
        notes=notes,
    )
    try:
        session.add(template)
        await session.flush()
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_RECURRING,
            entity_id=template.id,
            action=ACTION_CREATE,
            new_data=_snapshot(template),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return template


EDITABLE_FIELDS = frozenset(
    {"name", "amount_minor", "day_of_month", "category_id", "payment_method_id",
     "start_date", "notes", "is_active"}
)


async def update_template(
    session: AsyncSession, *, user: User, template: RecurringExpense, **changes
) -> RecurringExpense:
    """Şablonu günceller. Geçmişte üretilmiş kayıtlara dokunulmaz."""
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise RecurringError(f"Bilinmeyen alan: {', '.join(sorted(unknown))}")
    if "day_of_month" in changes:
        validate_day_of_month(changes["day_of_month"])
    if "amount_minor" in changes and changes["amount_minor"] <= 0:
        raise RecurringError("Tutar sıfırdan büyük olmalıdır")

    before = _snapshot(template)
    for field, value in changes.items():
        setattr(template, field, value)
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_RECURRING,
            entity_id=template.id,
            action=ACTION_UPDATE,
            old_data=before,
            new_data=_snapshot(template),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return template


async def delete_template(
    session: AsyncSession, *, user: User, template: RecurringExpense
) -> None:
    """Şablonu siler. Ondan üretilmiş harcamalar yerinde kalır."""
    before = _snapshot(template)
    template_id = template.id
    try:
        # Bag once bosaltilir: SQLite silinen bir kimligi yeni bir satira
        # verebilir ve eski harcamalar o kimlige bakiyor kalirsa yeni sablon
        # o ay uretim yapilmis sanilip atlanirdi.
        await session.execute(
            update(Expense)
            .where(Expense.recurring_expense_id == template_id)
            .values(recurring_expense_id=None)
        )
        await session.delete(template)
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_RECURRING,
            entity_id=template_id,
            action=ACTION_DELETE,
            old_data=before,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


# ---------------------------------------------------------------------------
# Aylık üretim
# ---------------------------------------------------------------------------


def scheduled_date(template: RecurringExpense, *, year: int, month: int) -> date:
    """Şablonun o aydaki kayıt tarihi.

    Ayın gün sayısı yetmiyorsa ayın son gününe düşer; kural taksit
    tarihleriyle aynıdır.
    """
    return normalized_date(year, month, template.day_of_month)


async def _already_generated(
    session: AsyncSession, template: RecurringExpense, *, year: int, month: int
) -> bool:
    start, end = month_bounds(year, month)
    existing = await session.scalar(
        select(Expense.id).where(
            Expense.recurring_expense_id == template.id,
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
    )
    return existing is not None


def _months_to_check(today: date) -> list[tuple[int, int]]:
    months = [(today.year, today.month)]
    for _ in range(CATCH_UP_MONTHS):
        year, month = months[-1]
        months.append((year - 1, 12) if month == 1 else (year, month - 1))
    return months


async def generate_due(
    session: AsyncSession, *, today: date, actor: User | None = None
) -> list[GeneratedExpense]:
    """Günü gelmiş sabit giderleri harcamaya çevirir.

    Kayıt tarihi **bugün değil, şablonun o aydaki günüdür**: eklenti üç gün
    kapalı kaldıysa kira yine ayın 1'ine yazılır, 4'üne değil.
    """
    generated: list[GeneratedExpense] = []
    templates = await list_templates(session)
    if not templates:
        return generated

    for template in templates:
        for year, month in _months_to_check(today):
            when = scheduled_date(template, year=year, month=month)
            if when > today or when < template.start_date:
                continue
            if await _already_generated(session, template, year=year, month=month):
                continue

            user = actor or await session.get(User, template.created_by_user_id)
            expense = await create_expense(
                session,
                user=user,
                data=ExpenseInput(
                    payment_method_id=template.payment_method_id,
                    category_id=template.category_id,
                    transaction_date=when,
                    amount=template.amount_minor,
                    description=template.name,
                    recurring_expense_id=template.id,
                ),
            )
            generated.append(
                GeneratedExpense(template_name=template.name, expense=expense)
            )
    return generated
