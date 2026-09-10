"""Harcama yaşam döngüsü: oluşturma, güncelleme, silme.

Bu modül sistemin tek yazma yoludur. Web sitesi ve Home Assistant paneli
buradan geçer; böylece iki giriş arasında hesaplama farkı oluşamaz.

Harcama ve taksitleri **tek transaction** içinde yazılır: yarım veri (taksitsiz
harcama) oluşamaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.audit_log import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_RESTORE,
    ACTION_UPDATE,
    ENTITY_EXPENSE,
)
from ..models.expense import Expense, format_public_id
from ..models.installment import STATUS_PAID, ExpenseInstallment
from ..models.payment_method import TYPE_CASH, PaymentMethod
from ..models.user import User
from . import tags
from .audit import record_audit
from .finance.installments import build_schedule
from .finance.money import parse_amount_to_minor

SINGLE_INSTALLMENT = 1

FINANCIAL_FIELDS = frozenset(
    {"total_amount_minor", "transaction_date", "payment_method_id", "installment_count"}
)
"""Değişmeleri hâlinde taksit planının yeniden üretilmesi gereken alanlar."""

EDITABLE_FIELDS = FINANCIAL_FIELDS | {
    "category_id",
    "description",
    "is_shared",
    "owner_user_id",
}


class ExpenseError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


@dataclass(frozen=True, slots=True)
class ExpenseInput:
    payment_method_id: int
    category_id: int
    transaction_date: date
    amount: str | int | Decimal
    installment_count: int = SINGLE_INSTALLMENT
    description: str | None = None
    recurring_expense_id: int | None = None
    is_shared: bool = True
    owner_user_id: int | None = None
    """Kişisel harcamanın sahibi. Verilirse harcama kişiseldir; `is_shared`
    yanlış verilip sahip boş bırakılırsa sahip kaydı giren kişidir."""


async def _resolve_owner(
    session: AsyncSession,
    *,
    is_shared: bool,
    owner_user_id: int | None,
    fallback_user_id: int,
) -> int | None:
    """Harcamanın sahibini bulur; ortaksa `None` döner."""
    if is_shared and owner_user_id is None:
        return None
    owner_id = owner_user_id or fallback_user_id
    owner = await session.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise ExpenseError("Kişisel harcamanın sahibi bulunamadı")
    return owner_id


async def _load_payment_method(
    session: AsyncSession, payment_method_id: int
) -> PaymentMethod:
    method = await session.get(PaymentMethod, payment_method_id)
    if method is None:
        raise ExpenseError("Ödeme yöntemi bulunamadı")
    if not method.is_active:
        raise ExpenseError(f"{method.name} pasif durumda, yeni harcamada kullanılamaz")
    return method


def _resolve_installment_count(method: PaymentMethod, requested: int) -> int:
    """Nakit ödemede taksit sayısını doğrular.

    Sessizce 1'e düşürmek yerine hatalı isteği reddeder: kullanıcı 3 taksit
    seçtiyse ve kayıt tek çekim olarak düşerse bunu fark etmesi gerekir.
    """
    if method.type == TYPE_CASH and requested != SINGLE_INSTALLMENT:
        raise ExpenseError("Nakit harcamalarda taksit kullanılamaz")
    return requested


def _snapshot_of(method: PaymentMethod) -> dict[str, object]:
    """Kart koşullarını harcamaya kopyalar.

    Kart ayarı sonradan değişse bile bu harcamanın planı yeniden hesaplanmaz.
    """
    return {
        "payment_method_type_snapshot": method.type,
        "payment_method_name_snapshot": method.name,
        "statement_day_snapshot": method.statement_day,
        "due_offset_days_snapshot": method.due_offset_days,
        "cutoff_inclusive_snapshot": (
            method.cutoff_inclusive if method.is_credit_card else None
        ),
    }


def _build_installments(
    *,
    total_amount_minor: int,
    installment_count: int,
    transaction_date: date,
    snapshot: dict[str, object],
) -> list[ExpenseInstallment]:
    """Anlik goruntudeki kart kosullarina gore taksit satirlarini uretir.

    Expense nesnesi yerine duz degerler alir: boylece kayit veritabanina
    yazilmadan once de cagrilabilir ve asenkron oturumda ortuk yukleme
    tetiklenmez.
    """
    schedule = build_schedule(
        total_minor=total_amount_minor,
        installment_count=installment_count,
        transaction_date=transaction_date,
        statement_day=snapshot["statement_day_snapshot"],
        due_offset_days=snapshot["due_offset_days_snapshot"],
        cutoff_inclusive=bool(snapshot["cutoff_inclusive_snapshot"]),
    )
    return [
        ExpenseInstallment(
            installment_number=line.number,
            installment_count=line.count,
            amount_minor=line.amount_minor,
            statement_date=line.statement_date,
            due_date=line.due_date,
        )
        for line in schedule
    ]


def _audit_payload(expense: Expense) -> dict[str, object]:
    return {
        "public_id": expense.public_id,
        "total_amount_minor": expense.total_amount_minor,
        "transaction_date": expense.transaction_date,
        "payment_method_id": expense.payment_method_id,
        "category_id": expense.category_id,
        "installment_count": expense.installment_count,
        "description": expense.description,
        "is_shared": expense.is_shared,
        "owner_user_id": expense.owner_user_id,
    }


def _has_paid_installment(expense: Expense) -> bool:
    return any(line.status == STATUS_PAID for line in expense.installments)


async def create_expense(
    session: AsyncSession, *, user: User, data: ExpenseInput
) -> Expense:
    """Harcamayı ve taksit planını tek transaction içinde oluşturur."""
    method = await _load_payment_method(session, data.payment_method_id)
    installment_count = _resolve_installment_count(method, data.installment_count)
    total_minor = parse_amount_to_minor(data.amount)
    owner_id = await _resolve_owner(
        session,
        is_shared=data.is_shared,
        owner_user_id=data.owner_user_id,
        fallback_user_id=user.id,
    )

    snapshot = _snapshot_of(method)
    expense = Expense(
        public_id="",
        created_by_user_id=user.id,
        payment_method_id=method.id,
        category_id=data.category_id,
        transaction_date=data.transaction_date,
        total_amount_minor=total_minor,
        installment_count=installment_count,
        description=data.description,
        recurring_expense_id=data.recurring_expense_id,
        is_shared=owner_id is None,
        owner_user_id=owner_id,
        # Taksitler kayit henuz gecici haldeyken baglanir; bu sayede
        # koleksiyona atama bir veritabani okumasi tetiklemez.
        installments=_build_installments(
            total_amount_minor=total_minor,
            installment_count=installment_count,
            transaction_date=data.transaction_date,
            snapshot=snapshot,
        ),
        **snapshot,
    )

    try:
        session.add(expense)
        await session.flush()
        expense.public_id = format_public_id(expense.id)
        # Etiketler harcamayla ayni transaction icinde yazilir: yarim veri
        # (etiketsiz harcama) olusamaz.
        await tags.sync_tags(session, expense)
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_EXPENSE,
            entity_id=expense.id,
            action=ACTION_CREATE,
            new_data=_audit_payload(expense),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(expense, attribute_names=["installments"])
    return expense


async def get_expense(
    session: AsyncSession, expense_id: int, *, include_deleted: bool = False
) -> Expense | None:
    statement = (
        select(Expense)
        .where(Expense.id == expense_id)
        .options(selectinload(Expense.installments))
    )
    if not include_deleted:
        statement = statement.where(Expense.deleted_at.is_(None))
    return await session.scalar(statement)


async def update_expense(
    session: AsyncSession, *, user: User, expense: Expense, changes: dict[str, object]
) -> Expense:
    """Harcamayı günceller ve gerekiyorsa taksit planını yeniden üretir.

    Tutar, tarih, ödeme yöntemi veya taksit sayısı değişirse plan baştan
    kurulur. Yalnızca açıklama veya kategori değişirse plana dokunulmaz.
    """
    if expense.deleted_at is not None:
        raise ExpenseError("Silinmiş harcama düzenlenemez")

    changes = dict(changes)
    if "amount" in changes:
        changes["total_amount_minor"] = parse_amount_to_minor(changes.pop("amount"))

    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ExpenseError(f"Düzenlenemeyen alan: {', '.join(sorted(unknown))}")

    if {"is_shared", "owner_user_id"} & set(changes):
        requested_owner = changes.pop("owner_user_id", None)
        shared = bool(changes.pop("is_shared", expense.is_shared)) and requested_owner is None
        owner_id = await _resolve_owner(
            session,
            is_shared=shared,
            owner_user_id=requested_owner,
            fallback_user_id=expense.owner_user_id or expense.created_by_user_id,
        )
        changes["owner_user_id"] = owner_id
        changes["is_shared"] = owner_id is None

    before = _audit_payload(expense)
    touches_finance = bool(FINANCIAL_FIELDS & set(changes))
    if touches_finance and _has_paid_installment(expense):
        raise ExpenseError(
            "Ödenmiş taksiti olan harcamanın tutarı, tarihi, kartı veya taksit "
            "sayısı değiştirilemez. Kaydı silip yeniden oluşturun."
        )

    try:
        for field, value in changes.items():
            setattr(expense, field, value)

        if touches_finance:
            method = await _load_payment_method(session, expense.payment_method_id)
            expense.installment_count = _resolve_installment_count(
                method, expense.installment_count
            )
            snapshot = _snapshot_of(method)
            for field, value in snapshot.items():
                setattr(expense, field, value)
            # Eski satirlar bellege alinmadan koleksiyona dokunulursa asenkron
            # oturumda ortuk okuma tetiklenir.
            await session.refresh(expense, attribute_names=["installments"])
            # Once silinip flush edilir, sonra yenileri eklenir. Tek adimda
            # atama yapilirsa SQLAlchemy yeni satirlari eskiler silinmeden
            # yazmaya calisir ve (expense_id, installment_number) tekillik
            # kisiti ihlal edilir.
            expense.installments.clear()
            await session.flush()
            expense.installments.extend(
                _build_installments(
                    total_amount_minor=expense.total_amount_minor,
                    installment_count=expense.installment_count,
                    transaction_date=expense.transaction_date,
                    snapshot=snapshot,
                )
            )

        if "description" in changes:
            # Aciklama duzenlendiyse eski etiketler kalmamalidir.
            await tags.sync_tags(session, expense)

        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_EXPENSE,
            entity_id=expense.id,
            action=ACTION_UPDATE,
            old_data=before,
            new_data=_audit_payload(expense),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(expense, attribute_names=["installments"])
    return expense


async def soft_delete_expense(
    session: AsyncSession, *, user: User, expense: Expense
) -> Expense:
    """Harcamayı yumuşak siler. Taksit satırları durur, raporlardan düşer."""
    if expense.deleted_at is not None:
        return expense
    try:
        expense.deleted_at = datetime.now(timezone.utc)
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_EXPENSE,
            entity_id=expense.id,
            action=ACTION_DELETE,
            old_data=_audit_payload(expense),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return expense


async def restore_expense(
    session: AsyncSession, *, user: User, expense: Expense
) -> Expense:
    """Yumuşak silinmiş harcamayı geri alır."""
    try:
        expense.deleted_at = None
        record_audit(
            session,
            user_id=user.id,
            entity_type=ENTITY_EXPENSE,
            entity_id=expense.id,
            action=ACTION_RESTORE,
            new_data=_audit_payload(expense),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return expense
