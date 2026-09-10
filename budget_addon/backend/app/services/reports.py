"""Raporlama.

Sistemde iki finansal bakış vardır ve bunlar **hiçbir zaman** aynı toplama
karışmaz:

- **Harcama (spending):** `expenses.total_amount_minor`, `transaction_date`
  ayına yazılır. Taksit sayısı bu raporu etkilemez.
- **Nakit akışı (cash flow):** `expense_installments.amount_minor`,
  `statement_date` veya `due_date` ayına yazılır.

12.000 TL / 12 taksitlik bir televizyon, alındığı ayın harcama raporunda
12.000 TL; aynı ayın ekstre yükünde 1.000 TL görünür. İkisini toplamak çift
sayma hatasıdır.

Ayrıntı için bkz. docs/FINANCE_RULES.md, bölüm 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Select, and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.category import Category
from ..models.expense import Expense
from ..models.installment import STATUS_CANCELLED, STATUS_PAID, ExpenseInstallment
from ..models.payment_method import TYPE_CASH, TYPE_CREDIT_CARD, PaymentMethod
from ..models.user import User
from ..utils.time import local_today, month_bounds
from . import refunds
from .finance.dates import MONTHS_PER_YEAR

BASIS_STATEMENT = "statement"
BASIS_DUE = "due"
CASH_FLOW_BASES = (BASIS_STATEMENT, BASIS_DUE)

DEFAULT_FORECAST_MONTHS = 12
INACTIVE_INSTALLMENT_STATUSES = (STATUS_PAID, STATUS_CANCELLED)


def _live_expenses() -> Select:
    """Yumuşak silinmiş harcamaları dışarıda bırakan temel sorgu.

    Tüm rapor sorguları buradan türetilir; filtreyi tek tek yazmak yerine
    merkezîleştirmek, bir raporda unutulup silinmiş kaydın toplama karışmasını
    engeller.
    """
    return select(Expense).where(Expense.deleted_at.is_(None))


def _live_installments() -> Select:
    return (
        select(ExpenseInstallment)
        .join(Expense, ExpenseInstallment.expense_id == Expense.id)
        .where(Expense.deleted_at.is_(None))
    )


# ---------------------------------------------------------------------------
# Harcama raporu
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NamedTotal:
    id: int
    name: str
    total_minor: int
    transaction_count: int = 0
    emoji: str = ""


@dataclass(frozen=True, slots=True)
class MonthlySpendingReport:
    """Bir ayın harcama özeti. Tutarlar harcama toplamıdır, taksit değil."""

    year: int
    month: int
    total_minor: int
    transaction_count: int
    cash_total_minor: int
    card_total_minor: int
    by_user: list[NamedTotal] = field(default_factory=list)
    by_category: list[NamedTotal] = field(default_factory=list)
    refunded_minor: int = 0
    """Ay içinde alınan iadelerin toplamı.

    `total_minor` bu tutar düşülmüş **net** harcamadır; iade ayrıca
    gösterilebilsin diye ham hâliyle de taşınır."""
    largest_expense: Expense | None = None

    @property
    def largest_category(self) -> NamedTotal | None:
        return self.by_category[0] if self.by_category else None


async def monthly_spending(
    session: AsyncSession, *, year: int, month: int
) -> MonthlySpendingReport:
    """§20'deki aylık harcama raporunu üretir."""
    start, end = month_bounds(year, month)
    in_month = (Expense.transaction_date >= start, Expense.transaction_date <= end)

    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(Expense.total_amount_minor), 0),
                func.count(Expense.id),
            )
            .where(Expense.deleted_at.is_(None), *in_month)
        )
    ).one()

    by_type = dict(
        (
            await session.execute(
                select(
                    Expense.payment_method_type_snapshot,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0),
                )
                .where(Expense.deleted_at.is_(None), *in_month)
                .group_by(Expense.payment_method_type_snapshot)
            )
        ).all()
    )

    by_user = [
        NamedTotal(id=row.id, name=row.display_name, total_minor=row.total, transaction_count=row.count)
        for row in (
            await session.execute(
                select(
                    User.id,
                    User.display_name,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0).label("total"),
                    func.count(Expense.id).label("count"),
                )
                .join(Expense, Expense.created_by_user_id == User.id)
                .where(Expense.deleted_at.is_(None), *in_month)
                .group_by(User.id, User.display_name)
                .order_by(func.sum(Expense.total_amount_minor).desc())
            )
        ).all()
    ]

    by_category = [
        NamedTotal(
            id=row.id,
            name=row.name,
            emoji=row.emoji,
            total_minor=row.total,
            transaction_count=row.count,
        )
        for row in (
            await session.execute(
                select(
                    Category.id,
                    Category.name,
                    Category.emoji,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0).label("total"),
                    func.count(Expense.id).label("count"),
                )
                .join(Expense, Expense.category_id == Category.id)
                .where(Expense.deleted_at.is_(None), *in_month)
                .group_by(Category.id, Category.name, Category.emoji)
                .order_by(func.sum(Expense.total_amount_minor).desc())
            )
        ).all()
    ]

    largest = await session.scalar(
        _live_expenses()
        .where(*in_month)
        .order_by(Expense.total_amount_minor.desc(), Expense.id)
        .limit(1)
    )

    # Iadeler her yerde ayni sekilde dusulur: rapor "net harcama" gosterir.
    # Tek noktadan yapilmasi, site, panel ve HA sensorlerinin ayni sayiyi
    # gormesini garanti eder.
    refunded_total = await refunds.total_in_month(session, year=year, month=month)
    refunded_cash = await refunds.cash_total_in_month(session, year=year, month=month)
    refunded_by_category = await refunds.by_category_in_month(
        session, year=year, month=month
    )
    by_category = _net_categories(by_category, refunded_by_category)

    return MonthlySpendingReport(
        year=year,
        month=month,
        total_minor=totals[0] - refunded_total,
        transaction_count=totals[1],
        cash_total_minor=by_type.get(TYPE_CASH, 0) - refunded_cash,
        card_total_minor=(
            by_type.get(TYPE_CREDIT_CARD, 0) - (refunded_total - refunded_cash)
        ),
        by_user=by_user,
        by_category=by_category,
        refunded_minor=refunded_total,
        largest_expense=largest,
    )


def _net_categories(
    categories: list[NamedTotal], refunded: dict[int, int]
) -> list[NamedTotal]:
    """Kategori toplamlarından iadeleri düşer ve sırayı yeniden kurar.

    Sıralama yeniden yapılır: iade sonrası en yüksek kategori değişmiş
    olabilir ve rapor sıralamayı ham tutara göre bırakırsa yanıltır.
    """
    if not refunded:
        return categories
    netted = [
        NamedTotal(
            id=item.id,
            name=item.name,
            emoji=item.emoji,
            total_minor=item.total_minor - refunded.get(item.id, 0),
            transaction_count=item.transaction_count,
        )
        for item in categories
    ]
    return sorted(netted, key=lambda item: item.total_minor, reverse=True)


# ---------------------------------------------------------------------------
# Ekstre raporu
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StatementSummary:
    payment_method_id: int
    payment_method_name: str
    statement_date: date
    due_date: date
    total_minor: int
    installment_count: int


async def upcoming_statements(
    session: AsyncSession, *, since: date, until: date | None = None
) -> list[StatementSummary]:
    """§21'deki kart bazlı ekstre raporunu üretir.

    Yalnızca kredi kartı taksitleri toplanır; nakit harcamaların ekstresi
    olmadığı için bu rapora girmez.
    """
    conditions = [
        ExpenseInstallment.statement_date >= since,
        Expense.payment_method_type_snapshot == TYPE_CREDIT_CARD,
        ExpenseInstallment.status.not_in(INACTIVE_INSTALLMENT_STATUSES),
    ]
    if until is not None:
        conditions.append(ExpenseInstallment.statement_date <= until)

    rows = (
        await session.execute(
            select(
                Expense.payment_method_id,
                Expense.payment_method_name_snapshot,
                ExpenseInstallment.statement_date,
                ExpenseInstallment.due_date,
                func.sum(ExpenseInstallment.amount_minor).label("total"),
                func.count(ExpenseInstallment.id).label("count"),
            )
            .join(Expense, ExpenseInstallment.expense_id == Expense.id)
            .where(Expense.deleted_at.is_(None), *conditions)
            .group_by(
                Expense.payment_method_id,
                Expense.payment_method_name_snapshot,
                ExpenseInstallment.statement_date,
                ExpenseInstallment.due_date,
            )
            .order_by(ExpenseInstallment.statement_date, Expense.payment_method_name_snapshot)
        )
    ).all()

    # Iade, dustugu ekstreye alacak yazilir. Taksit satirlarina dokunulmaz:
    # gecmis yeniden hesaplanmaz, yalnizca ekstre toplami netlesir.
    credits = {
        (credit.payment_method_id, credit.statement_date): credit.total_minor
        for credit in await refunds.statement_credits(session, since=since)
    }

    return [
        StatementSummary(
            payment_method_id=row.payment_method_id,
            payment_method_name=row.payment_method_name_snapshot,
            statement_date=row.statement_date,
            due_date=row.due_date,
            total_minor=row.total
            - credits.get((row.payment_method_id, row.statement_date), 0),
            installment_count=row.count,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Aktif taksit raporu
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActiveInstallmentPlan:
    expense_id: int
    public_id: str
    description: str | None
    category_name: str
    payment_method_name: str
    total_minor: int
    installment_count: int
    settled_count: int
    remaining_minor: int

    @property
    def paid_position(self) -> str:
        """`4/12` biçiminde ilerleme göstergesi."""
        return f"{self.settled_count}/{self.installment_count}"

    @property
    def monthly_minor(self) -> int:
        """Yaklaşık aylık yük. Kuruş farkları nedeniyle tam bölünmeyebilir."""
        return self.total_minor // self.installment_count


async def active_installment_plans(
    session: AsyncSession, today: date | None = None
) -> list[ActiveInstallmentPlan]:
    """§22'deki aktif taksitli alışverişleri listeler.

    Son ödeme tarihi geçmiş taksit ödenmiş sayılır. Tüm taksitleri ödenmiş
    veya iptal edilmiş bir harcama listede yer almaz.
    """
    open_line = and_(
        ExpenseInstallment.status.not_in(INACTIVE_INSTALLMENT_STATUSES),
        ExpenseInstallment.due_date >= (today or local_today()),
    )
    remaining = func.sum(ExpenseInstallment.amount_minor).filter(open_line)
    settled = func.count(ExpenseInstallment.id).filter(not_(open_line))

    rows = (
        await session.execute(
            select(
                Expense.id,
                Expense.public_id,
                Expense.description,
                Expense.total_amount_minor,
                Expense.installment_count,
                Expense.payment_method_name_snapshot,
                Category.name.label("category_name"),
                func.coalesce(remaining, 0).label("remaining"),
                settled.label("settled"),
            )
            .join(ExpenseInstallment, ExpenseInstallment.expense_id == Expense.id)
            .join(Category, Expense.category_id == Category.id)
            .where(
                Expense.deleted_at.is_(None),
                Expense.installment_count > 1,
            )
            .group_by(Expense.id, Category.name)
            .having(func.coalesce(remaining, 0) > 0)
            .order_by(func.coalesce(remaining, 0).desc())
        )
    ).all()

    return [
        ActiveInstallmentPlan(
            expense_id=row.id,
            public_id=row.public_id,
            description=row.description,
            category_name=row.category_name,
            payment_method_name=row.payment_method_name_snapshot,
            total_minor=row.total_amount_minor,
            installment_count=row.installment_count,
            settled_count=row.settled,
            remaining_minor=row.remaining,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Gelecek ödeme yükü
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonthlyObligation:
    year: int
    month: int
    total_minor: int
    installment_count: int


def _basis_column(basis: str):
    if basis == BASIS_STATEMENT:
        return ExpenseInstallment.statement_date
    if basis == BASIS_DUE:
        return ExpenseInstallment.due_date
    raise ValueError(f"Geçersiz bakış açısı: {basis!r}")


async def future_obligations(
    session: AsyncSession,
    *,
    start: date,
    months: int = DEFAULT_FORECAST_MONTHS,
    basis: str = BASIS_STATEMENT,
    include_cash: bool = False,
) -> list[MonthlyObligation]:
    """§23'teki gelecek kredi kartı yükünü ay ay üretir.

    `basis` ile ekstre bazlı ya da son ödeme bazlı bakış seçilir. Arayüz hangi
    bakışın gösterildiğini açıkça yazmalıdır; iki tablo aynı harcamayı farklı
    aylara dağıtır ve karıştırılırsa yanıltıcı olur.

    Nakit harcamalar varsayılan olarak **dışarıda bırakılır**: bu rapor ileriye
    dönük bir borç tablosudur ve nakit ödeme işlem anında tamamlanmıştır.
    Nakdin plan satırı işlem gününe yazıldığı için filtrelenmeseydi içinde
    bulunulan ayın yükünü olduğundan yüksek gösterirdi.

    Harcaması olmayan aylar da sıfır tutarla döner, böylece grafik ve liste
    boşluk göstermez.
    """
    column = _basis_column(basis)
    first_day, _ = month_bounds(start.year, start.month)
    last_month_absolute = start.year * MONTHS_PER_YEAR + (start.month - 1) + months - 1
    end_year, end_month_index = divmod(last_month_absolute, MONTHS_PER_YEAR)
    _, last_day = month_bounds(end_year, end_month_index + 1)

    rows = (
        await session.execute(
            select(
                func.strftime("%Y", column).label("year"),
                func.strftime("%m", column).label("month"),
                func.sum(ExpenseInstallment.amount_minor).label("total"),
                func.count(ExpenseInstallment.id).label("count"),
            )
            .join(Expense, ExpenseInstallment.expense_id == Expense.id)
            .where(
                Expense.deleted_at.is_(None),
                ExpenseInstallment.status.not_in(INACTIVE_INSTALLMENT_STATUSES),
                column >= first_day,
                column <= last_day,
                *(
                    ()
                    if include_cash
                    else (Expense.payment_method_type_snapshot != TYPE_CASH,)
                ),
            )
            .group_by("year", "month")
        )
    ).all()

    totals = {(int(row.year), int(row.month)): (row.total, row.count) for row in rows}

    obligations = []
    for offset in range(months):
        absolute = start.year * MONTHS_PER_YEAR + (start.month - 1) + offset
        year, month_index = divmod(absolute, MONTHS_PER_YEAR)
        month = month_index + 1
        total, count = totals.get((year, month), (0, 0))
        obligations.append(
            MonthlyObligation(
                year=year, month=month, total_minor=total, installment_count=count
            )
        )
    return obligations


# ---------------------------------------------------------------------------
# Yıllık karşılaştırma
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonthComparison:
    """Bir ayın bu yılki ve geçen yılki net harcaması."""

    month: int
    this_year_minor: int
    last_year_minor: int

    @property
    def difference_minor(self) -> int:
        return self.this_year_minor - self.last_year_minor

    @property
    def change_percent(self) -> int | None:
        """Yüzde değişim. Geçen yıl kayıt yoksa oran hesaplanmaz."""
        if self.last_year_minor <= 0:
            return None
        return round(self.difference_minor * 100 / self.last_year_minor)


@dataclass(frozen=True, slots=True)
class YearComparison:
    """Bir yılın aylık dökümü ve önceki yılla karşılaştırması."""

    year: int
    months: list[MonthComparison] = field(default_factory=list)

    @property
    def this_year_total_minor(self) -> int:
        return sum(item.this_year_minor for item in self.months)

    @property
    def last_year_total_minor(self) -> int:
        return sum(item.last_year_minor for item in self.months)

    @property
    def difference_minor(self) -> int:
        return self.this_year_total_minor - self.last_year_total_minor

    @property
    def busiest_month(self) -> MonthComparison | None:
        recorded = [item for item in self.months if item.this_year_minor > 0]
        return max(recorded, key=lambda item: item.this_year_minor, default=None)


async def _net_month_total(session: AsyncSession, *, year: int, month: int) -> int:
    """Bir ayın iadeler düşülmüş harcama toplamı."""
    start, end = month_bounds(year, month)
    spent = await session.scalar(
        select(func.coalesce(func.sum(Expense.total_amount_minor), 0)).where(
            Expense.deleted_at.is_(None),
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
    )
    refunded = await refunds.total_in_month(session, year=year, month=month)
    return spent - refunded


async def yearly_comparison(session: AsyncSession, *, year: int) -> YearComparison:
    """Ayları geçen yılın aynı aylarıyla karşılaştırır.

    Kıyas aynı ayla yapılır, önceki ayla değil: harcama mevsimseldir ve
    ocak ile aralığı yan yana koymak yanıltır.
    """
    months = []
    for month in range(1, MONTHS_PER_YEAR + 1):
        months.append(
            MonthComparison(
                month=month,
                this_year_minor=await _net_month_total(
                    session, year=year, month=month
                ),
                last_year_minor=await _net_month_total(
                    session, year=year - 1, month=month
                ),
            )
        )
    return YearComparison(year=year, months=months)
