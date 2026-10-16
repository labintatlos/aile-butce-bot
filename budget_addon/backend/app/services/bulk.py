"""Toplu düzenleme, toplu silme, geri alma ve açıklama birleştirme.

Her toplu işlem **tek transaction**dır: yirmi harcamanın on dokuzu değişip
biri hata verirse hiçbiri değişmez. Değişiklik yine `services/expenses.py`
üzerinden yapılır; denetim kaydı, etiket eşitlemesi ve doğrulama tek tek
düzenlemeyle birebir aynıdır.

İşlem, değiştirdiği alanların **önceki** değerlerini döndürür. Arayüz bunu
saklar ve "Geri al" denince `revert` ile aynen geri yazar; geri alma da tek
transaction'dır.

Toplu düzenleme yalnızca taksit planına dokunmayan alanları değiştirir
(kategori, ortak/kişisel, açıklama, etiket). Tutar, tarih ve kart toplu
değiştirilemez: her biri taksit planını yeniden kurar ve ödenmiş taksitleri
olan bir harcamada reddedilir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.category import Category
from ..models.expense import Expense
from ..models.user import User
from . import rules as rules_service
from . import tags
from .category_suggest import normalise
from .expenses import ExpenseError, restore_expense, soft_delete_expense, update_expense

MAX_BULK = 500
REVERTIBLE_FIELDS = ("category_id", "description", "is_shared", "owner_user_id")


class BulkError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


@dataclass(frozen=True, slots=True)
class PreviousValues:
    """Bir harcamanın toplu işlemden önceki değiştirilebilir alanları."""

    expense_id: int
    category_id: int
    description: str | None
    is_shared: bool
    owner_user_id: int | None


@dataclass(slots=True)
class BulkResult:
    changed: list[int] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)
    previous: list[PreviousValues] = field(default_factory=list)


def _previous(expense: Expense) -> PreviousValues:
    return PreviousValues(
        expense_id=expense.id,
        category_id=expense.category_id,
        description=expense.description,
        is_shared=expense.is_shared,
        owner_user_id=expense.owner_user_id,
    )


async def _load(session: AsyncSession, ids: list[int], *, deleted: bool = False) -> list[Expense]:
    unique = list(dict.fromkeys(ids))
    if not unique:
        raise BulkError("Hiç harcama seçilmedi")
    if len(unique) > MAX_BULK:
        raise BulkError(f"Tek seferde en fazla {MAX_BULK} harcama değiştirilebilir")
    condition = Expense.deleted_at.is_not(None) if deleted else Expense.deleted_at.is_(None)
    rows = (
        await session.scalars(
            select(Expense)
            .where(Expense.id.in_(unique), condition)
            .options(selectinload(Expense.installments), selectinload(Expense.splits))
        )
    ).all()
    by_id = {row.id: row for row in rows}
    return [by_id[expense_id] for expense_id in unique if expense_id in by_id]


def _with_tag(description: str | None, tag: str) -> str:
    folded = tags.extract_tags(f"#{tag}")
    if not folded:
        raise BulkError("Geçersiz etiket")
    if folded[0] in tags.extract_tags(description):
        return description or ""
    return f"{description or ''} #{folded[0]}".strip()


def _without_tag(description: str | None, tag: str) -> str | None:
    folded = tags.extract_tags(f"#{tag}")
    if not folded or not description:
        return description
    words = [
        word
        for word in description.split()
        if not (word.startswith("#") and tags.extract_tags(word) == folded)
    ]
    return " ".join(words) or None


async def bulk_update(
    session: AsyncSession, *, user: User, ids: list[int], changes: dict[str, Any]
) -> BulkResult:
    """Seçilen harcamalara aynı değişikliği uygular.

    Desteklenen anahtarlar: `category_id`, `is_shared` / `owner_user_id`,
    `add_tag`, `remove_tag`. Bölünmüş harcamanın kategorisi değişmez; o
    harcama `skipped` altında gerekçesiyle döner.
    """
    allowed = {"category_id", "is_shared", "owner_user_id", "add_tag", "remove_tag"}
    unknown = set(changes) - allowed
    if unknown:
        raise BulkError(f"Toplu değiştirilemeyen alan: {', '.join(sorted(unknown))}")
    if not changes:
        raise BulkError("Değiştirilecek bir şey seçilmedi")
    if "category_id" in changes:
        category = await session.get(Category, changes["category_id"])
        if category is None or not category.is_active:
            raise BulkError("Kategori bulunamadı")

    result = BulkResult()
    try:
        for expense in await _load(session, ids):
            own: dict[str, Any] = {}
            if "category_id" in changes and changes["category_id"] != expense.category_id:
                if expense.splits:
                    result.skipped[expense.id] = "Bölünmüş harcamanın kategorisi parçalardan değişir"
                else:
                    own["category_id"] = changes["category_id"]
            if "is_shared" in changes or "owner_user_id" in changes:
                own["is_shared"] = changes.get("is_shared", expense.is_shared)
                own["owner_user_id"] = changes.get("owner_user_id")
            description = expense.description
            if changes.get("add_tag"):
                description = _with_tag(description, changes["add_tag"])
            if changes.get("remove_tag"):
                description = _without_tag(description, changes["remove_tag"])
            if description != expense.description:
                own["description"] = description
            if not own:
                continue
            before = _previous(expense)
            await update_expense(session, user=user, expense=expense, changes=own, commit=False)
            result.changed.append(expense.id)
            result.previous.append(before)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


async def revert(
    session: AsyncSession, *, user: User, items: list[dict[str, Any]]
) -> BulkResult:
    """Toplu işlemden önceki değerleri aynen geri yazar."""
    by_id = {int(item["expense_id"]): item for item in items}
    result = BulkResult()
    try:
        for expense in await _load(session, list(by_id)):
            item = by_id[expense.id]
            own = {name: item.get(name) for name in REVERTIBLE_FIELDS if name in item}
            if expense.splits:
                own.pop("category_id", None)
            before = _previous(expense)
            await update_expense(session, user=user, expense=expense, changes=own, commit=False)
            result.changed.append(expense.id)
            result.previous.append(before)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


async def bulk_delete(session: AsyncSession, *, user: User, ids: list[int]) -> BulkResult:
    result = BulkResult()
    try:
        for expense in await _load(session, ids):
            await soft_delete_expense(session, user=user, expense=expense, commit=False)
            result.changed.append(expense.id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


async def bulk_restore(session: AsyncSession, *, user: User, ids: list[int]) -> BulkResult:
    result = BulkResult()
    try:
        for expense in await _load(session, ids, deleted=True):
            await restore_expense(session, user=user, expense=expense, commit=False)
            result.changed.append(expense.id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


# ---------------------------------------------------------------------------
# Açıklamalar (satıcılar)
# ---------------------------------------------------------------------------

DESCRIPTION_SCAN_LIMIT = 5_000


@dataclass(frozen=True, slots=True)
class DescriptionGroup:
    """Sadeleştirildiğinde aynı olan açıklamalar."""

    key: str
    sample: str
    """Bu gruptaki en yeni harcamanın açıklaması, etiketleri çıkarılmış."""
    count: int
    total_minor: int


async def description_groups(
    session: AsyncSession, *, query: str | None = None, limit: int = 100
) -> list[DescriptionGroup]:
    """Açıklamaları sadeleştirilmiş hâllerine göre gruplar.

    "MIGROS", "Migros" ve "migros #tatil" tek grupta toplanır. En çok
    kullanılan önce gelir.
    """
    needle = normalise(query) if query else ""
    rows = (
        await session.execute(
            select(Expense.description, Expense.total_amount_minor)
            .where(Expense.deleted_at.is_(None), Expense.description.is_not(None))
            .order_by(Expense.id.desc())
            .limit(DESCRIPTION_SCAN_LIMIT)
        )
    ).all()
    counts: dict[str, int] = defaultdict(int)
    totals: dict[str, int] = defaultdict(int)
    samples: dict[str, str] = {}
    for description, amount in rows:
        key = normalise(description)
        if not key or (needle and needle not in key):
            continue
        counts[key] += 1
        totals[key] += amount
        if key not in samples:
            samples[key] = " ".join(
                word for word in description.split() if not word.startswith("#")
            )
    groups = [
        DescriptionGroup(key=key, sample=samples[key], count=counts[key], total_minor=totals[key])
        for key in counts
    ]
    groups.sort(key=lambda group: (-group.count, group.key))
    return groups[:limit]


async def merge_descriptions(
    session: AsyncSession,
    *,
    user: User,
    keys: list[str],
    target: str,
    create_rule: bool = False,
) -> BulkResult:
    """Farklı yazılmış açıklamaları tek bir ada çevirir.

    Etiketler korunur. `create_rule` açıksa her eski yazım için bir kural da
    eklenir; böylece aynı yazım bir daha geldiğinde formda, içe aktarmada ve
    hızlı girişte doğru ada çevrilir.
    """
    clean_target = " ".join((target or "").split())
    if not clean_target:
        raise BulkError("Yeni açıklamayı yazın")
    wanted = {normalise(key) for key in keys if normalise(key)}
    if not wanted:
        raise BulkError("Birleştirilecek açıklama seçilmedi")

    matching = (
        await session.scalars(
            select(Expense.id).where(
                Expense.deleted_at.is_(None), Expense.description.is_not(None)
            )
        )
    ).all()
    result = BulkResult()
    try:
        for expense in await _load_all(session, list(matching)):
            if normalise(expense.description) not in wanted:
                continue
            renamed = rules_service.keep_tags(expense.description, clean_target)
            if renamed == expense.description:
                continue
            before = _previous(expense)
            await update_expense(
                session,
                user=user,
                expense=expense,
                changes={"description": renamed},
                commit=False,
            )
            result.changed.append(expense.id)
            result.previous.append(before)
        if create_rule:
            for key in sorted(wanted):
                if key == normalise(clean_target):
                    continue
                await rules_service.create_rule(
                    session,
                    user=user,
                    values={"pattern": key, "match_type": "equals", "set_description": clean_target},
                    commit=False,
                )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


async def _load_all(session: AsyncSession, ids: list[int]) -> list[Expense]:
    """`_load` gibi, ama üst sınır olmadan ve boş listeye izin vererek."""
    if not ids:
        return []
    return list(
        (
            await session.scalars(
                select(Expense)
                .where(Expense.id.in_(ids), Expense.deleted_at.is_(None))
                .options(selectinload(Expense.installments), selectinload(Expense.splits))
            )
        ).all()
    )


async def apply_rule(session: AsyncSession, *, user: User, rule_id: int) -> BulkResult:
    """Bir kuralı geçmiş harcamalara uygular (bkz. `rules.plan_for_rule`)."""
    rule = await session.get(rules_service.Rule, rule_id)
    if rule is None:
        raise BulkError("Kural bulunamadı")
    plans = await rules_service.plan_for_rule(session, rule)
    result = BulkResult()
    try:
        for plan in plans:
            before = _previous(plan.expense)
            try:
                await update_expense(
                    session, user=user, expense=plan.expense, changes=plan.changes, commit=False
                )
            except ExpenseError as exc:
                result.skipped[plan.expense.id] = str(exc)
                continue
            result.changed.append(plan.expense.id)
            result.previous.append(before)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result
