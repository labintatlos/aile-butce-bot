"""Rapor ve dışa aktarma uç noktaları. Yalnızca okur.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını
çağırır, sonucu biçimlendirir.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .expenses_api import expense_out, reload_expense
from .models.user import User
from .schemas import (
    BudgetStatusOut,
    CardUsageOut,
    InstallmentPlanOut,
    Money,
    MonthComparisonOut,
    MonthForecastOut,
    MonthlyPositionOut,
    MonthlySpendingOut,
    NamedTotalOut,
    ObligationOut,
    ObligationsOut,
    PersonalBudgetOut,
    StatementOut,
    TagTotalOut,
    YearComparisonOut,
)
from .security.identity import current_user
from .services import (
    budgets,
    cards,
    cashflow,
    exporting,
    forecast,
    personal_budgets,
    reports,
    tags,
)
from .utils.time import local_today

router = APIRouter()


BASIS_LABELS = {
    reports.BASIS_STATEMENT: "Ekstre Bazlı",
    reports.BASIS_DUE: "Son Ödeme Bazlı",
}


def _named_total(item: reports.NamedTotal) -> NamedTotalOut:
    return NamedTotalOut(
        id=item.id,
        name=item.name,
        emoji=item.emoji,
        total=Money.of(item.total_minor),
        transaction_count=item.transaction_count,
    )


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
        largest = expense_out(await reload_expense(session, report.largest_expense.id))
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
                Money.of(usage.limit_minor) if usage.has_limit else None
            ),
            outstanding=Money.of(usage.outstanding_minor),
            available=Money.of(usage.available_minor),
            ratio=usage.ratio,
            is_over_limit=usage.is_over_limit,
        )
        for usage in await cards.card_usage(session)
    ]


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
