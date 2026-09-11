"""HTTP arayüzü.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını çağırır,
sonucu biçimlendirir. Web sitesi ve Home Assistant paneli aynı servisleri
çağırdığı için iki giriş arasında hesaplama farkı oluşamaz.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.category import Category
from .models.payment_method import DEFAULT_CURRENCY, PaymentMethod
from .models.user import User
from .schemas import (
    BootstrapOut,
    CategoryOut,
    ExpenseCreateIn,
    ExpenseOut,
    ExpenseUpdateIn,
    InstallmentOut,
    InstallmentPlanOut,
    MonthlySpendingOut,
    Money,
    NamedTotalOut,
    ObligationOut,
    ObligationsOut,
    PersonalBudgetIn,
    PersonalBudgetOut,
    CategoryCreateIn,
    CategoryUpdateIn,
    PaymentMethodCreateIn,
    PaymentMethodOut,
    PaymentMethodUpdateIn,
    BudgetStatusOut,
    CardUsageOut,
    IncomeCreateIn,
    IncomeOut,
    MonthComparisonOut,
    MonthForecastOut,
    MonthlyPositionOut,
    RecurringExpenseCreateIn,
    RecurringExpenseOut,
    RecurringExpenseUpdateIn,
    RefundCreateIn,
    RefundOut,
    SchedulePreviewIn,
    SearchResultOut,
    TagTotalOut,
    YearComparisonOut,
    SchedulePreviewOut,
    StatementOut,
    UserOut,
)
from .security.identity import current_user
from .services import (
    budgets,
    cards,
    cashflow,
    exporting,
    forecast,
    income as income_service,
    personal_budgets,
    recurring,
    refunds,
    reports,
    tags,
    search as search_service,
    settings_service,
)
from .services.expenses import (
    ExpenseError,
    ExpenseInput,
    create_expense,
    get_expense,
    soft_delete_expense,
    update_expense,
)
from .services.finance.installments import build_schedule
from .services.finance.money import parse_amount_to_minor
from .utils.time import local_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

BASIS_LABELS = {
    reports.BASIS_STATEMENT: "Ekstre Bazlı",
    reports.BASIS_DUE: "Son Ödeme Bazlı",
}


def _expense_out(expense) -> ExpenseOut:
    today = local_today()
    return ExpenseOut(
        id=expense.id,
        public_id=expense.public_id,
        created_by=expense.created_by.display_name if expense.created_by else "",
        category=CategoryOut.model_validate(expense.category),
        payment_method_id=expense.payment_method_id,
        payment_method_name=expense.payment_method_name_snapshot,
        transaction_date=expense.transaction_date,
        total=Money.of(expense.total_amount_minor),
        installment_count=expense.installment_count,
        description=expense.description,
        is_shared=expense.is_shared,
        owner_user_id=expense.owner_user_id,
        owner_name=expense.owner.display_name if expense.owner else None,
        has_receipt=bool(expense.receipt_path),
        installments=[
            InstallmentOut(
                number=line.installment_number,
                count=line.installment_count,
                amount=Money.of(line.amount_minor),
                statement_date=line.statement_date,
                due_date=line.due_date,
                status=_installment_status(line, today),
            )
            for line in expense.installments
        ],
    )


def _installment_status(line, today) -> str:
    """Son ödeme tarihi geçmiş taksit ödenmiş sayılır."""
    if line.status == "scheduled" and line.due_date < today:
        return "paid"
    return line.status


def _named_total(item: reports.NamedTotal) -> NamedTotalOut:
    return NamedTotalOut(
        id=item.id,
        name=item.name,
        emoji=item.emoji,
        total=Money.of(item.total_minor),
        transaction_count=item.transaction_count,
    )


# ---------------------------------------------------------------------------
# Acilis
# ---------------------------------------------------------------------------


@router.get("/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BootstrapOut:
    """Arayüzün açılışta ihtiyaç duyduğu her şey tek istekte."""
    categories = (
        await session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
    ).all()
    methods = (
        await session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.is_active.is_(True))
            .order_by(PaymentMethod.type, PaymentMethod.name)
        )
    ).all()
    people = (
        await session.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.id)
        )
    ).all()
    return BootstrapOut(
        user=UserOut.model_validate(user),
        categories=[CategoryOut.model_validate(c) for c in categories],
        payment_methods=[PaymentMethodOut.model_validate(m) for m in methods],
        people=[UserOut.model_validate(p) for p in people],
        today=local_today(settings.timezone),
        currency=DEFAULT_CURRENCY,
    )


# ---------------------------------------------------------------------------
# Harcamalar
# ---------------------------------------------------------------------------


@router.post("/expenses/preview", response_model=SchedulePreviewOut)
async def preview_schedule(
    payload: SchedulePreviewIn,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SchedulePreviewOut:
    """Kaydetmeden önce taksit ve ekstre özetini hesaplar (§17).

    Hiçbir şey yazmaz; yalnızca kaydedilecek olanı gösterir.
    """
    method = await session.get(PaymentMethod, payload.payment_method_id)
    if method is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme yöntemi bulunamadı")
    try:
        total_minor = parse_amount_to_minor(payload.amount)
        schedule = build_schedule(
            total_minor=total_minor,
            installment_count=payload.installment_count,
            transaction_date=payload.transaction_date,
            statement_day=method.statement_day,
            due_offset_days=method.due_offset_days,
            cutoff_inclusive=method.cutoff_inclusive,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return SchedulePreviewOut(
        total=Money.of(total_minor),
        installment_count=len(schedule),
        installment_amount=Money.of(schedule[0].amount_minor),
        first_statement_date=schedule[0].statement_date if method.is_credit_card else None,
        first_due_date=schedule[0].due_date if method.is_credit_card else None,
        last_due_date=schedule[-1].due_date if method.is_credit_card else None,
        is_credit_card=method.is_credit_card,
    )


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ExpenseCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    try:
        expense = await create_expense(
            session,
            user=user,
            data=ExpenseInput(
                payment_method_id=payload.payment_method_id,
                category_id=payload.category_id,
                transaction_date=payload.transaction_date,
                amount=payload.amount,
                installment_count=payload.installment_count,
                description=payload.description,
                is_shared=payload.is_shared,
                owner_user_id=payload.owner_user_id,
            ),
        )
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _expense_out(await _reload(session, expense.id))


async def _reload(session: AsyncSession, expense_id: int):
    from sqlalchemy.orm import selectinload

    from .models.expense import Expense

    return await session.scalar(
        select(Expense)
        .where(Expense.id == expense_id)
        .options(
            selectinload(Expense.installments),
            selectinload(Expense.category),
            selectinload(Expense.created_by),
        )
    )


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
async def read(
    expense_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")
    return _expense_out(await _reload(session, expense_id))


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def edit(
    expense_id: int,
    payload: ExpenseUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ExpenseOut:
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _expense_out(await _reload(session, expense_id))
    try:
        await update_expense(session, user=user, expense=expense, changes=changes)
    except (ExpenseError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _expense_out(await _reload(session, expense_id))


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    expense_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    expense = await get_expense(session, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Harcama bulunamadı")
    await soft_delete_expense(session, user=user, expense=expense)


# ---------------------------------------------------------------------------
# Raporlar
# ---------------------------------------------------------------------------


@router.get("/reports/spending/monthly", response_model=MonthlySpendingOut)
async def monthly_spending_report(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    owner: str | None = Query(default=None, pattern=r"^(shared|\d+)$"),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MonthlySpendingOut:
    """Aylık **harcama** raporu. Tutarlar harcama toplamıdır, taksit değil.

    `owner=shared` yalnızca ortak, `owner=<kişi>` o kişinin kişisel
    harcamalarını gösterir."""
    today = local_today(settings.timezone)
    report = await reports.monthly_spending(
        session, year=year or today.year, month=month or today.month, owner=owner
    )
    largest = None
    if report.largest_expense is not None:
        largest = _expense_out(await _reload(session, report.largest_expense.id))
    return MonthlySpendingOut(
        year=report.year,
        month=report.month,
        total=Money.of(report.total_minor),
        transaction_count=report.transaction_count,
        cash_total=Money.of(report.cash_total_minor),
        card_total=Money.of(report.card_total_minor),
        by_user=[_named_total(item) for item in report.by_user],
        by_category=[_named_total(item) for item in report.by_category],
        largest_expense=largest,
    )


@router.get("/reports/personal-budgets", response_model=list[PersonalBudgetOut])
async def personal_budget_report(
    year: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[PersonalBudgetOut]:
    """Kişi başı yıllık kişisel bütçe, harcanan ve kalan."""
    today = local_today(settings.timezone)
    items = await personal_budgets.yearly_status(
        session, year=year or today.year, today=today
    )
    return [
        PersonalBudgetOut(
            user_id=item.user_id,
            name=item.name,
            year=item.year,
            budget=Money.of(item.budget_minor) if item.budget_minor is not None else None,
            spent=Money.of(item.spent_minor),
            remaining=(
                Money.of(item.remaining_minor) if item.remaining_minor is not None else None
            ),
            ratio=item.ratio,
            is_exceeded=item.is_exceeded,
            expense_count=item.expense_count,
            year_elapsed_ratio=item.year_elapsed_ratio,
        )
        for item in items
    ]


@router.put("/personal-budgets/{user_id}", response_model=list[PersonalBudgetOut])
async def set_personal_budget(
    user_id: int,
    payload: PersonalBudgetIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[PersonalBudgetOut]:
    """Bir kişinin o yılki kişisel bütçesini belirler; boş tutar kaldırır."""
    try:
        amount = (
            parse_amount_to_minor(payload.amount)
            if payload.amount and payload.amount.strip()
            else None
        )
        await personal_budgets.set_budget(
            session, user_id=user_id, year=payload.year, amount_minor=amount
        )
    except (personal_budgets.PersonalBudgetError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await personal_budget_report(
        year=payload.year, _user=user, session=session, settings=settings
    )


@router.get("/reports/cashflow/statements", response_model=list[StatementOut])
async def statements_report(
    since: date | None = None,
    until: date | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[StatementOut]:
    """Kart bazlı yaklaşan ekstreler. **Nakit akışı** bakışıdır."""
    rows = await reports.upcoming_statements(
        session, since=since or local_today(settings.timezone), until=until
    )
    return [
        StatementOut(
            payment_method_id=row.payment_method_id,
            payment_method_name=row.payment_method_name,
            statement_date=row.statement_date,
            due_date=row.due_date,
            total=Money.of(row.total_minor),
            installment_count=row.installment_count,
        )
        for row in rows
    ]


@router.get("/reports/cashflow/upcoming", response_model=ObligationsOut)
async def upcoming_obligations(
    months: int = Query(default=reports.DEFAULT_FORECAST_MONTHS, ge=1, le=36),
    basis: str = Query(default=reports.BASIS_STATEMENT),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ObligationsOut:
    """Gelecek kredi kartı yükü. Hangi bakış kullanıldığı yanıtta yazar."""
    if basis not in BASIS_LABELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Geçersiz bakış açısı")
    rows = await reports.future_obligations(
        session, start=local_today(settings.timezone), months=months, basis=basis
    )
    return ObligationsOut(
        basis=basis,
        basis_label=BASIS_LABELS[basis],
        months=[
            ObligationOut(
                year=row.year,
                month=row.month,
                total=Money.of(row.total_minor),
                installment_count=row.installment_count,
            )
            for row in rows
        ],
    )


@router.get("/reports/installments", response_model=list[InstallmentPlanOut])
async def installment_plans(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[InstallmentPlanOut]:
    """Aktif taksitli alışverişler ve kalan borç."""
    plans = await reports.active_installment_plans(session)
    return [
        InstallmentPlanOut(
            expense_id=plan.expense_id,
            public_id=plan.public_id,
            description=plan.description,
            category_name=plan.category_name,
            payment_method_name=plan.payment_method_name,
            total=Money.of(plan.total_minor),
            remaining=Money.of(plan.remaining_minor),
            monthly=Money.of(plan.monthly_minor),
            position=plan.paid_position,
        )
        for plan in plans
    ]


# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------


@router.get("/payment-methods", response_model=list[PaymentMethodOut])
async def read_payment_methods(
    include_inactive: bool = False,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentMethodOut]:
    methods = await settings_service.list_payment_methods(
        session, include_inactive=include_inactive
    )
    return [PaymentMethodOut.model_validate(m) for m in methods]


@router.post(
    "/payment-methods", response_model=PaymentMethodOut, status_code=status.HTTP_201_CREATED
)
async def add_payment_method(
    payload: PaymentMethodCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PaymentMethodOut:
    try:
        method = await settings_service.create_payment_method(
            session, user=user, **payload.model_dump()
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return PaymentMethodOut.model_validate(method)


@router.patch("/payment-methods/{method_id}", response_model=PaymentMethodOut)
async def edit_payment_method(
    method_id: int,
    payload: PaymentMethodUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PaymentMethodOut:
    """Kart ayarlarını düzeltir. Geçmiş taksit planları değişmez."""
    method = await session.get(PaymentMethod, method_id)
    if method is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme yöntemi bulunamadı")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return PaymentMethodOut.model_validate(method)
    try:
        await settings_service.update_payment_method(
            session, user=user, method=method, changes=changes
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return PaymentMethodOut.model_validate(method)


@router.get("/categories", response_model=list[CategoryOut])
async def read_categories(
    include_inactive: bool = False,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryOut]:
    categories = await settings_service.list_categories(
        session, include_inactive=include_inactive
    )
    return [CategoryOut.model_validate(c) for c in categories]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def add_category(
    payload: CategoryCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    try:
        category = await settings_service.create_category(
            session, user=user, **payload.model_dump()
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return CategoryOut.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def edit_category(
    category_id: int,
    payload: CategoryUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategori bulunamadı")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if changes.get("monthly_budget_minor") == 0:
        # Sifir "hedefi kaldir" demektir: exclude_none bir null govdeyi zaten
        # eliyor, dolayisiyla silme niyetini tasiyacak baska bir deger yok.
        changes["monthly_budget_minor"] = None
    if not changes:
        return CategoryOut.model_validate(category)
    try:
        await settings_service.update_category(
            session, user=user, category=category, changes=changes
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return CategoryOut.model_validate(category)


# ---------------------------------------------------------------------------
# Arama
# ---------------------------------------------------------------------------


@router.get("/expenses", response_model=SearchResultOut)
async def search(
    text: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
    payment_method_id: int | None = None,
    created_by_user_id: int | None = None,
    min_amount_minor: int | None = Query(default=None, ge=0),
    max_amount_minor: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=search_service.DEFAULT_PAGE_SIZE, ge=1, le=search_service.MAX_PAGE_SIZE),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SearchResultOut:
    """Harcama arama ve filtreleme (§25)."""
    result = await search_service.search_expenses(
        session,
        search_service.SearchFilters(
            text=text,
            date_from=date_from,
            date_to=date_to,
            category_id=category_id,
            payment_method_id=payment_method_id,
            created_by_user_id=created_by_user_id,
            min_amount_minor=min_amount_minor,
            max_amount_minor=max_amount_minor,
        ),
        page=page,
        page_size=page_size,
    )
    return SearchResultOut(
        items=[_expense_out(expense) for expense in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
        has_next=result.has_next,
    )


@router.delete("/payment-methods/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_payment_method(
    method_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Kullanılmayan bir ödeme yöntemini siler.

    Harcamalarda kullanılıyorsa `409` döner; çağıran tarafın onu pasife alması
    beklenir. Silmek, geçmiş harcamaların ödeme yöntemini okunamaz hâle
    getirirdi.
    """
    method = await session.get(PaymentMethod, method_id)
    if method is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme yöntemi bulunamadı")
    try:
        await settings_service.delete_payment_method(session, user=user, method=method)
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_category(
    category_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Kullanılmayan bir kategoriyi siler; kullanılıyorsa `409` döner."""
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategori bulunamadı")
    try:
        await settings_service.delete_category(session, user=user, category=category)
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


# ---------------------------------------------------------------------------
# Sabit giderler
# ---------------------------------------------------------------------------


def _recurring_out(template) -> RecurringExpenseOut:
    return RecurringExpenseOut(
        id=template.id,
        name=template.name,
        category_id=template.category_id,
        payment_method_id=template.payment_method_id,
        amount=Money.of(template.amount_minor),
        day_of_month=template.day_of_month,
        start_date=template.start_date,
        notes=template.notes,
        is_active=template.is_active,
    )


@router.get("/recurring", response_model=list[RecurringExpenseOut])
async def read_recurring(
    include_inactive: bool = True,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RecurringExpenseOut]:
    templates = await recurring.list_templates(
        session, include_inactive=include_inactive
    )
    return [_recurring_out(template) for template in templates]


@router.post(
    "/recurring",
    response_model=RecurringExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_recurring(
    payload: RecurringExpenseCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringExpenseOut:
    try:
        template = await recurring.create_template(
            session,
            user=user,
            name=payload.name,
            category_id=payload.category_id,
            payment_method_id=payload.payment_method_id,
            amount=payload.amount_minor,
            day_of_month=payload.day_of_month,
            start_date=payload.start_date,
            notes=payload.notes,
        )
    except (recurring.RecurringError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _recurring_out(template)


@router.patch("/recurring/{template_id}", response_model=RecurringExpenseOut)
async def edit_recurring(
    template_id: int,
    payload: RecurringExpenseUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringExpenseOut:
    template = await recurring.get_template(session, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sabit gider bulunamadı")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _recurring_out(template)
    try:
        await recurring.update_template(session, user=user, template=template, **changes)
    except (recurring.RecurringError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _recurring_out(template)


@router.delete("/recurring/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recurring(
    template_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    template = await recurring.get_template(session, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sabit gider bulunamadı")
    await recurring.delete_template(session, user=user, template=template)


@router.get("/reports/budgets", response_model=list[BudgetStatusOut])
async def budget_report(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[BudgetStatusOut]:
    """Hedefi olan kategorilerin bu aydaki durumu."""
    today = local_today(settings.timezone)
    statuses = await budgets.monthly_status(
        session, year=year or today.year, month=month or today.month
    )
    return [
        BudgetStatusOut(
            category_id=status.category_id,
            name=status.name,
            emoji=status.emoji,
            budget=Money.of(status.budget_minor),
            spent=Money.of(status.spent_minor),
            remaining=Money.of(status.remaining_minor),
            ratio=status.ratio,
            is_exceeded=status.is_exceeded,
        )
        for status in statuses
    ]


# ---------------------------------------------------------------------------
# Gelirler ve nakit durumu
# ---------------------------------------------------------------------------


def _income_out(record) -> IncomeOut:
    return IncomeOut(
        id=record.id,
        source=record.source,
        amount=Money.of(record.amount_minor),
        received_date=record.received_date,
        notes=record.notes,
    )


@router.get("/incomes", response_model=list[IncomeOut])
async def read_incomes(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[IncomeOut]:
    today = local_today(settings.timezone)
    records = await income_service.list_incomes(
        session, year=year or today.year, month=month or today.month
    )
    return [_income_out(record) for record in records]


@router.post("/incomes", response_model=IncomeOut, status_code=status.HTTP_201_CREATED)
async def add_income(
    payload: IncomeCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> IncomeOut:
    try:
        record = await income_service.create_income(
            session,
            user=user,
            amount=payload.amount_minor,
            received_date=payload.received_date or local_today(settings.timezone),
            source=payload.source,
            notes=payload.notes,
        )
    except (income_service.IncomeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _income_out(record)


@router.delete("/incomes/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_income(
    income_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    record = await income_service.get_income(session, income_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gelir kaydı bulunamadı")
    await income_service.soft_delete_income(session, user=user, record=record)


@router.get("/reports/position", response_model=MonthlyPositionOut)
async def position_report(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MonthlyPositionOut:
    """Bu ayın nakit durumu: gelir, çıkışlar ve kalan."""
    report = await cashflow.monthly_position(
        session, today=local_today(settings.timezone)
    )
    return MonthlyPositionOut(
        year=report.year,
        month=report.month,
        income=Money.of(report.income_minor),
        card_due=Money.of(report.card_due_minor),
        cash_spent=Money.of(report.cash_spent_minor),
        expected_recurring=Money.of(report.expected_recurring_minor),
        outflow=Money.of(report.outflow_minor),
        remaining=Money.of(report.remaining_minor),
    )


@router.get("/reports/cards", response_model=list[CardUsageOut])
async def card_usage_report(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CardUsageOut]:
    """Kartların borç ve kullanılabilir limit durumu."""
    return [
        CardUsageOut(
            payment_method_id=usage.payment_method_id,
            name=usage.name,
            credit_limit=(
                Money.of(usage.credit_limit_minor) if usage.has_limit else None
            ),
            outstanding=Money.of(usage.outstanding_minor),
            available=Money.of(usage.available_minor),
            ratio=usage.ratio,
            is_over_limit=usage.is_over_limit,
        )
        for usage in await cards.card_usage(session)
    ]


# ---------------------------------------------------------------------------
# İadeler
# ---------------------------------------------------------------------------


def _refund_out(refund) -> RefundOut:
    return RefundOut(
        id=refund.id,
        expense_id=refund.expense_id,
        amount=Money.of(refund.amount_minor),
        refund_date=refund.refund_date,
        statement_date=refund.statement_date,
        due_date=refund.due_date,
        notes=refund.notes,
    )


@router.get("/expenses/{expense_id}/refunds", response_model=list[RefundOut])
async def read_refunds(
    expense_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RefundOut]:
    return [
        _refund_out(refund)
        for refund in await refunds.list_for_expense(session, expense_id)
    ]


@router.post(
    "/expenses/{expense_id}/refunds",
    response_model=RefundOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_refund(
    expense_id: int,
    payload: RefundCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RefundOut:
    try:
        refund = await refunds.create_refund(
            session,
            user=user,
            expense_id=expense_id,
            amount=payload.amount_minor,
            refund_date=payload.refund_date or local_today(settings.timezone),
            notes=payload.notes,
        )
    except refunds.RefundError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _refund_out(refund)


@router.delete("/refunds/{refund_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_refund(
    refund_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    refund = await refunds.get_refund(session, refund_id)
    if refund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "İade kaydı bulunamadı")
    await refunds.soft_delete_refund(session, user=user, refund=refund)


@router.get("/reports/tags", response_model=list[TagTotalOut])
async def tag_report(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TagTotalOut]:
    """Etiket toplamları. Yıl ve ay verilmezse bütün zamanlar toplanır."""
    return [
        TagTotalOut(
            tag=item.tag,
            total=Money.of(item.total_minor),
            transaction_count=item.transaction_count,
        )
        for item in await tags.totals(session, year=year, month=month)
    ]


@router.get("/reports/forecast", response_model=MonthForecastOut)
async def forecast_report(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MonthForecastOut:
    """Bu gidişle ay sonunda ne olacağı."""
    estimate = await forecast.month_forecast(
        session, today=local_today(settings.timezone)
    )
    return MonthForecastOut(
        year=estimate.year,
        month=estimate.month,
        days_elapsed=estimate.days_elapsed,
        days_in_month=estimate.days_in_month,
        spent_so_far=Money.of(estimate.spent_so_far_minor),
        fixed=Money.of(estimate.fixed_minor),
        variable_forecast=Money.of(estimate.variable_forecast_minor),
        variable_run_rate=Money.of(estimate.variable_run_rate_minor),
        variable_history=Money.of(estimate.variable_history_minor),
        total=Money.of(estimate.total_minor),
        remaining=Money.of(estimate.remaining_minor),
    )


@router.get("/reports/yearly", response_model=YearComparisonOut)
async def yearly_report(
    year: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> YearComparisonOut:
    """Ayları geçen yılın aynı aylarıyla karşılaştırır."""
    target = year or local_today(settings.timezone).year
    comparison = await reports.yearly_comparison(session, year=target)
    return YearComparisonOut(
        year=comparison.year,
        months=[
            MonthComparisonOut(
                month=item.month,
                this_year=Money.of(item.this_year_minor),
                last_year=Money.of(item.last_year_minor),
                change_percent=item.change_percent,
            )
            for item in comparison.months
        ],
        this_year_total=Money.of(comparison.this_year_total_minor),
        last_year_total=Money.of(comparison.last_year_total_minor),
    )


@router.get("/export/expenses.csv", response_class=PlainTextResponse)
async def export_expenses(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    """Harcamaları CSV olarak indirir. Ay verilmezse bütün yıl gelir."""
    today = local_today(settings.timezone)
    target_year = year or today.year
    start, end = exporting.month_range(target_year, month)
    content = await exporting.expenses_csv(session, start=start, end=end)
    filename = exporting.filename_for(year=target_year, month=month)
    return PlainTextResponse(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/incomes.csv", response_class=PlainTextResponse)
async def export_incomes(
    year: int | None = None,
    month: int | None = None,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    """Gelirleri CSV olarak indirir."""
    today = local_today(settings.timezone)
    target_year = year or today.year
    start, end = exporting.month_range(target_year, month)
    content = await exporting.incomes_csv(session, start=start, end=end)
    filename = exporting.filename_for(year=target_year, month=month, kind="gelir")
    return PlainTextResponse(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )