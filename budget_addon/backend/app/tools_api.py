"""Kurallar, açıklama birleştirme, ekstre içe aktarma ve mutabakat uç noktaları.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını
çağırır, sonucu biçimlendirir.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .expenses_api import bulk_out
from .models.rule import Rule
from .models.user import User
from .schemas import (
    BulkResultOut,
    ColumnMappingIn,
    DescriptionGroupOut,
    ImportCommitIn,
    ImportCommitOut,
    ImportPreviewIn,
    ImportPreviewOut,
    ImportPreviewRowOut,
    MergeDescriptionsIn,
    Money,
    ReconcileClearIn,
    ReconcileDetailOut,
    ReconcileLineOut,
    ReconcileSaveIn,
    ReconcileSummaryOut,
    RuleIn,
    RuleOut,
    RuleTestOut,
    RuleUpdateIn,
)
from .security.identity import current_user
from .services import bulk, importer, reconcile
from .services import rules as rules_service
from .services.expenses import ExpenseError
from .utils.time import local_today

router = APIRouter()

UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


@router.get("/rules", response_model=list[RuleOut])
async def read_rules(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RuleOut]:
    return [RuleOut.model_validate(rule) for rule in await rules_service.list_rules(session)]


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def add_rule(
    payload: RuleIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RuleOut:
    try:
        rule = await rules_service.create_rule(
            session, user=user, values=payload.model_dump(exclude_none=True)
        )
    except rules_service.RuleError as exc:
        await session.rollback()
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return RuleOut.model_validate(rule)


async def _rule(session: AsyncSession, rule_id: int) -> Rule:
    rule = await session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kural bulunamadı")
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut)
async def edit_rule(
    rule_id: int,
    payload: RuleUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RuleOut:
    rule = await _rule(session, rule_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True, exclude={"clear"})
    for name in payload.clear:
        if name in {"set_category_id", "set_payment_method_id", "set_description"}:
            changes[name] = None
    try:
        await rules_service.update_rule(session, user=user, rule=rule, changes=changes)
    except rules_service.RuleError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return RuleOut.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_rule(
    rule_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await rules_service.delete_rule(session, user=user, rule=await _rule(session, rule_id))


@router.get("/rules/test", response_model=RuleTestOut)
async def test_rules(
    description: str = Query("", max_length=500),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RuleTestOut:
    """Bir açıklamaya hangi kuralların ne uygulayacağını gösterir. Hiçbir şey yazmaz."""
    outcome = await rules_service.outcome_for(session, description)
    return RuleTestOut(
        category_id=outcome.category_id,
        payment_method_id=outcome.payment_method_id,
        description=outcome.description,
        rule_ids=list(outcome.rule_ids),
    )


@router.get("/rules/{rule_id}/preview", response_model=list[int])
async def preview_rule(
    rule_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[int]:
    """Kural geçmişe uygulanırsa değişecek harcamaların kimlikleri."""
    plans = await rules_service.plan_for_rule(session, await _rule(session, rule_id))
    return [plan.expense.id for plan in plans]


@router.post("/rules/{rule_id}/apply", response_model=BulkResultOut)
async def apply_rule(
    rule_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> BulkResultOut:
    """Kuralı geçmiş harcamalara uygular; önceki değerleri geri alma için döndürür."""
    try:
        result = await bulk.apply_rule(session, user=user, rule_id=rule_id)
    except (bulk.BulkError, ExpenseError) as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return bulk_out(result)


# ---------------------------------------------------------------------------
# Açıklamalar
# ---------------------------------------------------------------------------


@router.get("/descriptions", response_model=list[DescriptionGroupOut])
async def read_descriptions(
    q: str | None = Query(default=None, max_length=100),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DescriptionGroupOut]:
    """Farklı yazılmış ama aynı olan açıklamaları gruplar."""
    groups = await bulk.description_groups(session, query=q)
    return [
        DescriptionGroupOut(
            key=group.key, sample=group.sample, count=group.count, total=Money.of(group.total_minor)
        )
        for group in groups
    ]


@router.post("/descriptions/merge", response_model=BulkResultOut)
async def merge_descriptions(
    payload: MergeDescriptionsIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> BulkResultOut:
    try:
        result = await bulk.merge_descriptions(
            session,
            user=user,
            keys=payload.keys,
            target=payload.target,
            create_rule=payload.create_rule,
        )
    except (bulk.BulkError, rules_service.RuleError, ExpenseError) as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return bulk_out(result)


# ---------------------------------------------------------------------------
# İçe aktarma
# ---------------------------------------------------------------------------


@router.post("/import/preview", response_model=ImportPreviewOut)
async def import_preview(
    payload: ImportPreviewIn,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ImportPreviewOut:
    """Ekstreyi okur ve önerilen satırları döndürür. Hiçbir şey kaydetmez."""
    mapping = (
        importer.ColumnMapping(**payload.mapping.model_dump()) if payload.mapping else None
    )
    try:
        result = await importer.preview(
            session,
            text=payload.text,
            payment_method_id=payload.payment_method_id,
            default_category_id=payload.default_category_id,
            sign=payload.sign,
            mapping=mapping,
        )
    except importer.ImportFileError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return ImportPreviewOut(
        delimiter=result.delimiter,
        mapping=ColumnMappingIn(
            date_column=result.mapping.date_column,
            description_column=result.mapping.description_column,
            amount_column=result.mapping.amount_column,
            first_row=result.mapping.first_row,
        ),
        sign=result.sign,
        columns=result.columns,
        rows=[
            ImportPreviewRowOut(
                index=row.index,
                transaction_date=row.transaction_date,
                description=row.description,
                amount=Money.of(row.amount_minor),
                category_id=row.category_id,
                category_source=row.category_source,
                payment_method_id=row.payment_method_id,
                installment_count=row.installment_count,
                installment_current=row.installment_current,
                duplicate_of=row.duplicate_of,
                skip_reason=row.skip_reason,
                selected=row.selected,
                note=row.note,
            )
            for row in result.rows
        ],
    )


@router.post("/import/commit", response_model=ImportCommitOut)
async def import_commit(
    payload: ImportCommitIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ImportCommitOut:
    """Seçilen satırları tek seferde kaydeder; biri hatalıysa hiçbiri kaydedilmez."""
    try:
        created = await importer.commit_rows(
            session,
            user=user,
            rows=[importer.ImportRow(**row.model_dump()) for row in payload.rows],
        )
    except importer.ImportFileError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return ImportCommitOut(
        created=len(created),
        total=Money.of(sum(expense.total_amount_minor for expense in created)),
        expense_ids=[expense.id for expense in created],
    )


# ---------------------------------------------------------------------------
# Mutabakat
# ---------------------------------------------------------------------------


def _summary_out(summary: reconcile.StatementSummary) -> ReconcileSummaryOut:
    difference = summary.difference_minor
    return ReconcileSummaryOut(
        statement_date=summary.statement_date,
        due_date=summary.due_date,
        ours_total=Money.of(summary.ours_total_minor),
        line_count=summary.line_count,
        cleared_count=summary.cleared_count,
        bank_total=(
            Money.of(summary.bank_total_minor) if summary.bank_total_minor is not None else None
        ),
        difference=Money.of(difference) if difference is not None else None,
        is_reconciled=summary.is_reconciled,
        changed_since=summary.changed_since,
    )


def _detail_out(detail: reconcile.StatementDetail) -> ReconcileDetailOut:
    return ReconcileDetailOut(
        summary=_summary_out(detail.summary),
        lines=[
            ReconcileLineOut(
                kind=line.kind,
                id=line.id,
                expense_id=line.expense_id,
                public_id=line.public_id,
                description=line.description,
                transaction_date=line.transaction_date,
                amount=Money.of(line.amount_minor),
                installment_number=line.installment_number,
                installment_count=line.installment_count,
                cleared=line.cleared,
            )
            for line in detail.lines
        ],
        cleared_total=Money.of(detail.cleared_total_minor),
        note=detail.note,
    )


@router.get("/reconcile/{payment_method_id}", response_model=list[ReconcileSummaryOut])
async def reconcile_statements(
    payment_method_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[ReconcileSummaryOut]:
    try:
        items = await reconcile.statements(
            session, payment_method_id=payment_method_id, today=local_today(settings.timezone)
        )
    except reconcile.ReconcileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [_summary_out(item) for item in items]


@router.get("/reconcile/{payment_method_id}/{statement_date}", response_model=ReconcileDetailOut)
async def reconcile_detail(
    payment_method_id: int,
    statement_date: date,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReconcileDetailOut:
    try:
        detail = await reconcile.detail(
            session, payment_method_id=payment_method_id, statement_date=statement_date
        )
    except reconcile.ReconcileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _detail_out(detail)


@router.post(
    "/reconcile/{payment_method_id}/{statement_date}/cleared", response_model=ReconcileDetailOut
)
async def reconcile_mark(
    payment_method_id: int,
    statement_date: date,
    payload: ReconcileClearIn,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReconcileDetailOut:
    """Satırları "bankada görüldü" olarak işaretler veya işareti kaldırır."""
    try:
        await reconcile.set_cleared(
            session,
            payment_method_id=payment_method_id,
            installment_ids=payload.installment_ids,
            cleared=payload.cleared,
        )
        detail = await reconcile.detail(
            session, payment_method_id=payment_method_id, statement_date=statement_date
        )
    except reconcile.ReconcileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _detail_out(detail)


@router.put("/reconcile/{payment_method_id}/{statement_date}", response_model=ReconcileDetailOut)
async def reconcile_save(
    payment_method_id: int,
    statement_date: date,
    payload: ReconcileSaveIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReconcileDetailOut:
    """Bankanın ekstre tutarını kaydeder ve farkı gösterir."""
    try:
        detail = await reconcile.save(
            session,
            user=user,
            payment_method_id=payment_method_id,
            statement_date=statement_date,
            bank_total_minor=payload.bank_total_minor,
            note=payload.note,
        )
    except reconcile.ReconcileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _detail_out(detail)


@router.delete(
    "/reconcile/{payment_method_id}/{statement_date}", status_code=status.HTTP_204_NO_CONTENT
)
async def reconcile_forget(
    payment_method_id: int,
    statement_date: date,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await reconcile.forget(
        session, payment_method_id=payment_method_id, statement_date=statement_date
    )
