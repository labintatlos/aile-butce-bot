"""Ödeme yöntemi ve kategori yönetimi.

Buradaki değişiklikler **geçmişe dokunmaz**. Bir kartın hesap kesim günü
değiştirildiğinde mevcut harcamaların taksit planı olduğu gibi kalır; yeni gün
yalnızca bundan sonra oluşturulan harcamalara uygulanır. Bunu sağlayan şey,
harcamanın kendi anlık görüntüsünü taşımasıdır (docs/FINANCE_RULES.md, E5).

Silme yerine pasife alma kullanılır: kayıtlı harcamalar kartlara ve
kategorilere bağlıdır, silinirlerse geçmiş raporlar okunamaz hâle gelirdi.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    ENTITY_CATEGORY,
    ENTITY_PAYMENT_METHOD,
)
from ..models.category import Category
from ..models.payment_method import (
    TYPE_CASH,
    TYPE_CREDIT_CARD,
    PaymentMethod,
)
from ..models.user import User
from ..services.finance.dates import MAX_DAY_OF_MONTH, MIN_DAY_OF_MONTH
from ..services.finance.statement import DEFAULT_DUE_OFFSET_DAYS, validate_due_offset
from .audit import record_audit

CARD_FIELDS = frozenset(
    {"name", "statement_day", "due_offset_days", "cutoff_inclusive",
     "credit_limit_minor", "owner_user_id", "notes", "is_active"}
)
CATEGORY_FIELDS = frozenset({"name", "emoji", "sort_order", "is_active"})


class SettingsError(Exception):
    """Kullanıcıya gösterilebilir yapılandırma hatası."""


def _validate_statement_day(statement_day: int | None) -> None:
    if statement_day is None:
        raise SettingsError("Hesap kesim günü zorunludur")
    if not MIN_DAY_OF_MONTH <= statement_day <= MAX_DAY_OF_MONTH:
        raise SettingsError(
            f"Hesap kesim günü {MIN_DAY_OF_MONTH} ile {MAX_DAY_OF_MONTH}"
            " arasında olmalıdır"
        )


def _validate_due_offset(offset_days: int) -> None:
    try:
        validate_due_offset(offset_days)
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc


def _card_snapshot(method: PaymentMethod) -> dict[str, object]:
    return {
        "name": method.name,
        "type": method.type,
        "statement_day": method.statement_day,
        "due_offset_days": method.due_offset_days,
        "cutoff_inclusive": method.cutoff_inclusive,
        "credit_limit_minor": method.credit_limit_minor,
        "is_active": method.is_active,
    }


async def list_payment_methods(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[PaymentMethod]:
    statement = select(PaymentMethod).order_by(PaymentMethod.type, PaymentMethod.name)
    if not include_inactive:
        statement = statement.where(PaymentMethod.is_active.is_(True))
    return list((await session.scalars(statement)).all())


async def create_payment_method(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    type: str,
    statement_day: int | None = None,
    due_offset_days: int = DEFAULT_DUE_OFFSET_DAYS,
    cutoff_inclusive: bool = True,
    owner_user_id: int | None = None,
    credit_limit_minor: int | None = None,
    notes: str | None = None,
) -> PaymentMethod:
    if type not in (TYPE_CASH, TYPE_CREDIT_CARD):
        raise SettingsError("Geçersiz ödeme yöntemi türü")
    if type == TYPE_CREDIT_CARD:
        _validate_statement_day(statement_day)
        _validate_due_offset(due_offset_days)
    else:
        statement_day = None

    if await session.scalar(select(PaymentMethod).where(PaymentMethod.name == name)):
        raise SettingsError(f"'{name}' adında bir ödeme yöntemi zaten var")

    method = PaymentMethod(
        name=name,
        type=type,
        statement_day=statement_day,
        due_offset_days=due_offset_days,
        cutoff_inclusive=cutoff_inclusive if type == TYPE_CREDIT_CARD else True,
        owner_user_id=owner_user_id,
        credit_limit_minor=credit_limit_minor,
        notes=notes,
    )
    try:
        session.add(method)
        await session.flush()
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_PAYMENT_METHOD,
            entity_id=method.id,
            action=ACTION_CREATE,
            new_data=_card_snapshot(method),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return method


async def update_payment_method(
    session: AsyncSession, *, user: User, method: PaymentMethod, changes: dict[str, object]
) -> PaymentMethod:
    """Kart ayarlarını günceller.

    Geçmiş harcamaların taksit planı **değişmez**: her harcama kendi anlık
    görüntüsünü taşır ve buradaki değişiklik yalnızca sonraki kayıtlara
    uygulanır.
    """
    unknown = set(changes) - CARD_FIELDS
    if unknown:
        raise SettingsError(f"Düzenlenemeyen alan: {', '.join(sorted(unknown))}")

    before = _card_snapshot(method)
    merged_statement = changes.get("statement_day", method.statement_day)
    if method.type == TYPE_CREDIT_CARD:
        _validate_statement_day(merged_statement)
        _validate_due_offset(changes.get("due_offset_days", method.due_offset_days))
    elif merged_statement is not None:
        raise SettingsError("Nakit ödemede hesap kesim günü olmaz")

    if "name" in changes:
        clash = await session.scalar(
            select(PaymentMethod).where(
                PaymentMethod.name == changes["name"], PaymentMethod.id != method.id
            )
        )
        if clash:
            raise SettingsError(f"'{changes['name']}' adında bir ödeme yöntemi zaten var")

    try:
        for field, value in changes.items():
            setattr(method, field, value)
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_PAYMENT_METHOD,
            entity_id=method.id,
            action=ACTION_UPDATE,
            old_data=before,
            new_data=_card_snapshot(method),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return method


async def list_categories(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[Category]:
    statement = select(Category).order_by(Category.sort_order, Category.name)
    if not include_inactive:
        statement = statement.where(Category.is_active.is_(True))
    return list((await session.scalars(statement)).all())


async def create_category(
    session: AsyncSession, *, user: User, name: str, emoji: str = "", sort_order: int = 0
) -> Category:
    if await session.scalar(select(Category).where(Category.name == name)):
        raise SettingsError(f"'{name}' adında bir kategori zaten var")
    category = Category(name=name, emoji=emoji, sort_order=sort_order)
    try:
        session.add(category)
        await session.flush()
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_CATEGORY,
            entity_id=category.id,
            action=ACTION_CREATE,
            new_data={"name": name, "emoji": emoji},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return category


async def update_category(
    session: AsyncSession, *, user: User, category: Category, changes: dict[str, object]
) -> Category:
    """Kategoriyi günceller. Taksit planlarına hiçbir etkisi yoktur (kural E2)."""
    unknown = set(changes) - CATEGORY_FIELDS
    if unknown:
        raise SettingsError(f"Düzenlenemeyen alan: {', '.join(sorted(unknown))}")

    before = {"name": category.name, "emoji": category.emoji, "is_active": category.is_active}
    if "name" in changes:
        clash = await session.scalar(
            select(Category).where(
                Category.name == changes["name"], Category.id != category.id
            )
        )
        if clash:
            raise SettingsError(f"'{changes['name']}' adında bir kategori zaten var")

    try:
        for field, value in changes.items():
            setattr(category, field, value)
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_CATEGORY,
            entity_id=category.id,
            action=ACTION_UPDATE,
            old_data=before,
            new_data={
                "name": category.name,
                "emoji": category.emoji,
                "is_active": category.is_active,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return category


async def count_expenses_for_payment_method(session: AsyncSession, method_id: int) -> int:
    """Karta bağlı harcama sayısı. Yumuşak silinmişler de sayılır.

    Silinmiş bir harcama geri alınabilir; kartı kaldırırsak geri alma
    kırılırdı.
    """
    from ..models.expense import Expense

    return await session.scalar(
        select(func.count(Expense.id)).where(Expense.payment_method_id == method_id)
    ) or 0


async def count_expenses_for_category(session: AsyncSession, category_id: int) -> int:
    from ..models.expense import Expense

    return await session.scalar(
        select(func.count(Expense.id)).where(Expense.category_id == category_id)
    ) or 0


async def delete_payment_method(
    session: AsyncSession, *, user: User, method: PaymentMethod
) -> None:
    """Ödeme yöntemini kalıcı olarak siler.

    Yalnızca hiçbir harcama bu yöntemi kullanmıyorsa silinir. Kullanılıyorsa
    `SettingsError` yükseltilir ve kullanıcı pasife almaya yönlendirilir:
    kaydı silmek, ona bağlı harcamaların ödeme yöntemini okunamaz hâle
    getirirdi ve geçmiş raporlar bozulurdu.
    """
    used_by = await count_expenses_for_payment_method(session, method.id)
    if used_by:
        raise SettingsError(
            f"'{method.name}' {used_by} harcamada kullanılıyor, silinemez. "
            "Bunun yerine pasife alabilirsin: yeni harcamalarda görünmez, "
            "geçmiş kayıtlar korunur."
        )
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_PAYMENT_METHOD,
            entity_id=method.id,
            action=ACTION_DELETE,
            old_data=_card_snapshot(method),
        )
        await session.delete(method)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def delete_category(
    session: AsyncSession, *, user: User, category: Category
) -> None:
    """Kategoriyi kalıcı olarak siler; kullanılıyorsa pasife almayı önerir."""
    used_by = await count_expenses_for_category(session, category.id)
    if used_by:
        raise SettingsError(
            f"'{category.name}' {used_by} harcamada kullanılıyor, silinemez. "
            "Bunun yerine pasife alabilirsin: yeni harcamalarda görünmez, "
            "geçmiş kayıtlar korunur."
        )
    try:
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_CATEGORY,
            entity_id=category.id,
            action=ACTION_DELETE,
            old_data={"name": category.name, "emoji": category.emoji},
        )
        await session.delete(category)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def set_active(
    session: AsyncSession, *, user: User, entity, active: bool
):
    """Kartı veya kategoriyi pasife alır / geri açar."""
    if isinstance(entity, PaymentMethod):
        return await update_payment_method(
            session, user=user, method=entity, changes={"is_active": active}
        )
    return await update_category(
        session, user=user, category=entity, changes={"is_active": active}
    )
