"""Otomatik kurallar: eşleştirme, yönetim ve geçmişe uygulama.

Bir kural "açıklama şuna uyarsa kategoriyi, ödeme yöntemini veya açıklamayı
şuna çevir" der. Kurallar `sort_order` sırasıyla denenir; bir alanı ilk
dolduran kural kazanır, sonrakiler o alana dokunamaz. Böylece özel bir kural
("migros sanal market" → Market) genel bir kuralın ("migros" → Market) önüne
konarak kolayca öne geçirilebilir.

Kuralın uygulandığı yerler:

- Harcama formunda ve hızlı girişte kategori önerisi (geçmiş kayıtlardan
  önce kural bakılır),
- Ekstre içe aktarmada önizleme,
- Kullanıcı isterse geçmiş harcamalara toplu uygulama.

Hiçbiri kullanıcıya sormadan kayıt yapmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import ACTION_CREATE, ACTION_DELETE, ACTION_UPDATE
from ..models.category import Category
from ..models.expense import Expense
from ..models.payment_method import PaymentMethod
from ..models.rule import MATCH_CONTAINS, MATCH_EQUALS, MATCH_STARTS_WITH, MATCH_TYPES, Rule
from ..models.user import User
from . import tags
from .audit import record_audit
from .category_suggest import normalise

ENTITY_RULE = "rule"
RULE_FIELDS = frozenset(
    {
        "pattern",
        "match_type",
        "set_category_id",
        "set_payment_method_id",
        "set_description",
        "sort_order",
        "is_active",
    }
)
MAX_PATTERN_LENGTH = 120


class RuleError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


def matches(rule: Rule, description: str | None) -> bool:
    """Açıklama kurala uyuyor mu. İki taraf da sadeleştirilerek karşılaştırılır."""
    text = normalise(description)
    pattern = normalise(rule.pattern)
    if not text or not pattern:
        return False
    if rule.match_type == MATCH_EQUALS:
        return text == pattern
    if rule.match_type == MATCH_STARTS_WITH:
        return text.startswith(pattern)
    return pattern in text


def keep_tags(description: str | None, new_text: str) -> str:
    """Açıklamayı yeniden adlandırırken içindeki `#etiket`leri korur."""
    found = tags.extract_tags(description)
    suffix = " ".join(f"#{tag}" for tag in found)
    return f"{new_text} {suffix}".strip() if suffix else new_text


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """Kuralların bir açıklamaya göre doldurduğu alanlar."""

    category_id: int | None = None
    payment_method_id: int | None = None
    description: str | None = None
    rule_ids: tuple[int, ...] = ()

    @property
    def matched(self) -> bool:
        return bool(self.rule_ids)


def evaluate(rules: list[Rule], description: str | None) -> RuleOutcome:
    """Kuralları sırayla dener; her alanı ilk dolduran kural kazanır."""
    category_id = payment_method_id = None
    new_description = None
    used: list[int] = []
    for rule in rules:
        if not rule.is_active or not matches(rule, description):
            continue
        hit = False
        if category_id is None and rule.set_category_id is not None:
            category_id = rule.set_category_id
            hit = True
        if payment_method_id is None and rule.set_payment_method_id is not None:
            payment_method_id = rule.set_payment_method_id
            hit = True
        if new_description is None and rule.set_description:
            new_description = keep_tags(description, rule.set_description)
            hit = True
        if hit:
            used.append(rule.id)
    return RuleOutcome(
        category_id=category_id,
        payment_method_id=payment_method_id,
        description=new_description,
        rule_ids=tuple(used),
    )


async def list_rules(session: AsyncSession, *, active_only: bool = False) -> list[Rule]:
    statement = select(Rule).order_by(Rule.sort_order, Rule.id)
    if active_only:
        statement = statement.where(Rule.is_active.is_(True))
    return list((await session.scalars(statement)).all())


async def outcome_for(session: AsyncSession, description: str | None) -> RuleOutcome:
    """Etkin kuralların bir açıklama için ne söylediği.

    Pasife alınmış kategori veya ödeme yöntemi önerilmez.
    """
    outcome = evaluate(await list_rules(session, active_only=True), description)
    category_id = outcome.category_id
    if category_id is not None:
        category = await session.get(Category, category_id)
        if category is None or not category.is_active:
            category_id = None
    method_id = outcome.payment_method_id
    if method_id is not None:
        method = await session.get(PaymentMethod, method_id)
        if method is None or not method.is_active:
            method_id = None
    return RuleOutcome(
        category_id=category_id,
        payment_method_id=method_id,
        description=outcome.description,
        rule_ids=outcome.rule_ids,
    )


# ---------------------------------------------------------------------------
# Yönetim
# ---------------------------------------------------------------------------


def _snapshot(rule: Rule) -> dict[str, Any]:
    return {field: getattr(rule, field) for field in sorted(RULE_FIELDS)}


async def _validate(session: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(values)
    if "pattern" in cleaned:
        pattern = normalise(cleaned["pattern"])
        if not pattern:
            raise RuleError("Kuralın arayacağı metni yazın")
        cleaned["pattern"] = pattern[:MAX_PATTERN_LENGTH]
    if "match_type" in cleaned and cleaned["match_type"] not in MATCH_TYPES:
        raise RuleError("Geçersiz eşleşme türü")
    if "set_description" in cleaned:
        text = " ".join((cleaned["set_description"] or "").split())
        cleaned["set_description"] = text[:MAX_PATTERN_LENGTH] or None
    if cleaned.get("set_category_id") is not None:
        if await session.get(Category, cleaned["set_category_id"]) is None:
            raise RuleError("Kategori bulunamadı")
    if cleaned.get("set_payment_method_id") is not None:
        if await session.get(PaymentMethod, cleaned["set_payment_method_id"]) is None:
            raise RuleError("Ödeme yöntemi bulunamadı")
    return cleaned


def _require_action(rule: Rule) -> None:
    if (
        rule.set_category_id is None
        and rule.set_payment_method_id is None
        and not rule.set_description
    ):
        raise RuleError("Kural en az bir şeyi değiştirmeli: kategori, ödeme yöntemi veya açıklama")


async def create_rule(
    session: AsyncSession, *, user: User, values: dict[str, Any], commit: bool = True
) -> Rule:
    cleaned = await _validate(session, values)
    if "pattern" not in cleaned:
        raise RuleError("Kuralın arayacağı metni yazın")
    rule = Rule(
        match_type=cleaned.pop("match_type", MATCH_CONTAINS),
        created_by_user_id=user.id,
        **cleaned,
    )
    _require_action(rule)
    session.add(rule)
    await session.flush()
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_RULE,
        entity_id=rule.id,
        action=ACTION_CREATE,
        new_data=_snapshot(rule),
    )
    if commit:
        await session.commit()
    return rule


async def update_rule(
    session: AsyncSession, *, user: User, rule: Rule, changes: dict[str, Any]
) -> Rule:
    unknown = set(changes) - RULE_FIELDS
    if unknown:
        raise RuleError(f"Düzenlenemeyen alan: {', '.join(sorted(unknown))}")
    cleaned = await _validate(session, changes)
    before = _snapshot(rule)
    for field, value in cleaned.items():
        setattr(rule, field, value)
    try:
        _require_action(rule)
    except RuleError:
        await session.rollback()
        raise
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_RULE,
        entity_id=rule.id,
        action=ACTION_UPDATE,
        old_data=before,
        new_data=_snapshot(rule),
    )
    await session.commit()
    return rule


async def delete_rule(session: AsyncSession, *, user: User, rule: Rule) -> None:
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_RULE,
        entity_id=rule.id,
        action=ACTION_DELETE,
        old_data=_snapshot(rule),
    )
    await session.delete(rule)
    await session.commit()


# ---------------------------------------------------------------------------
# Geçmiş harcamalara uygulama
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedChange:
    """Bir kuralın bir harcamada değiştireceği alanlar."""

    expense: Expense
    changes: dict[str, Any]


async def plan_for_rule(session: AsyncSession, rule: Rule) -> list[PlannedChange]:
    """Kural geçmiş harcamalara uygulanırsa neyin değişeceği.

    Ödeme yöntemi geçmişe uygulanmaz: kart değişirse taksit planı yeniden
    kurulur ve ödenmiş ekstreler bozulurdu. Bölünmüş harcamanın kategorisine
    dokunulmaz; parçaları kullanıcı belirlemiştir.
    """
    expenses = (
        await session.scalars(
            select(Expense)
            .where(Expense.deleted_at.is_(None), Expense.description.is_not(None))
            .order_by(Expense.transaction_date.desc(), Expense.id.desc())
        )
    ).all()
    plans = []
    for expense in expenses:
        if not matches(rule, expense.description):
            continue
        changes: dict[str, Any] = {}
        if (
            rule.set_category_id is not None
            and not expense.splits
            and expense.category_id != rule.set_category_id
        ):
            changes["category_id"] = rule.set_category_id
        if rule.set_description:
            renamed = keep_tags(expense.description, rule.set_description)
            if renamed != expense.description:
                changes["description"] = renamed
        if changes:
            plans.append(PlannedChange(expense=expense, changes=changes))
    return plans
