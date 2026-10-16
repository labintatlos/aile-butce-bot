"""API şemaları.

Tutarlar dışarıya **kuruş** (`*_minor`) ve biçimlenmiş metin olarak birlikte
verilir: istemci hesaplama yapmak zorunda kalmaz, biçimlendirme tek yerden
gelir ve yuvarlama farkı oluşmaz.

Girişte tutar serbest metin olarak alınır (`"1.250,50"`), sunucu doğrular ve
kuruşa çevirir. İstemcinin gönderdiği bir kuruş değerine güvenilmez.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from .services.finance.money import MAX_INSTALLMENTS, MIN_INSTALLMENTS, format_try


class Money(BaseModel):
    minor: int
    formatted: str

    @classmethod
    def of(cls, minor: int) -> Money:
        return cls(minor=minor, formatted=format_try(minor))


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: str
    is_active: bool
    monthly_budget_minor: int | None = None
    group_name: str | None = None
    rollover: bool = False


class CategorySuggestionOut(BaseModel):
    """Geçmiş kayıtlardan önerilen kategori; öneri yoksa boş."""

    category_id: int | None = None


class PaymentMethodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    is_active: bool
    statement_day: int | None = None
    due_offset_days: int = 10
    cutoff_inclusive: bool = True
    owner_user_id: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    role: str


class BootstrapOut(BaseModel):
    """Arayüzün açılışta ihtiyaç duyduğu her şey tek istekte."""

    user: UserOut
    categories: list[CategoryOut]
    payment_methods: list[PaymentMethodOut]
    people: list[UserOut] = Field(default_factory=list)
    """Kişisel harcama seçicisi için etkin kişiler."""
    today: date
    currency: str
    max_installments: int = MAX_INSTALLMENTS


class SplitIn(BaseModel):
    """Bölünmüş harcamanın bir parçası. Tutar serbest metindir."""

    category_id: int
    amount: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=200)


class SplitOut(BaseModel):
    category_id: int
    category_name: str
    category_emoji: str = ""
    amount: Money
    note: str | None = None


class ExpenseCreateIn(BaseModel):
    payment_method_id: int
    category_id: int
    transaction_date: date
    amount: str = Field(min_length=1, max_length=32)
    installment_count: int = Field(
        default=MIN_INSTALLMENTS, ge=MIN_INSTALLMENTS, le=MAX_INSTALLMENTS
    )
    description: str | None = Field(default=None, max_length=500)
    is_shared: bool = True
    """Harcama ev/ortak mı, yoksa kişisel mi. Varsayılan ortaktır; kişisel
    olan sahibinin yıllık kişisel bütçesinden düşer."""
    owner_user_id: int | None = None
    """Kişisel harcamanın sahibi; verilirse harcama kişiseldir."""
    splits: list[SplitIn] = Field(default_factory=list, max_length=20)
    """İki veya daha fazla parça verilirse harcama bölünür; parçaların toplamı
    tutara eşit olmalıdır ve `category_id` en büyük parçanınki olur."""


class ExpenseUpdateIn(BaseModel):
    """Yalnızca gönderilen alanlar değiştirilir.

    `created_by_user_id` bilerek yer almaz: harcamanın sahibi doğrulanmış
    kimlikten gelir ve istemci tarafından değiştirilemez.
    """

    payment_method_id: int | None = None
    category_id: int | None = None
    transaction_date: date | None = None
    amount: str | None = Field(default=None, max_length=32)
    is_shared: bool | None = None
    owner_user_id: int | None = None
    installment_count: int | None = Field(
        default=None, ge=MIN_INSTALLMENTS, le=MAX_INSTALLMENTS
    )
    description: str | None = Field(default=None, max_length=500)
    splits: list[SplitIn] | None = Field(default=None, max_length=20)
    """Verilirse parçalar baştan yazılır; boş liste bölünmeyi kaldırır."""


class InstallmentOut(BaseModel):
    number: int
    count: int
    amount: Money
    statement_date: date
    due_date: date
    status: str


class ExpenseOut(BaseModel):
    id: int
    public_id: str
    created_by: str
    category: CategoryOut
    payment_method_id: int | None = None
    payment_method_name: str
    transaction_date: date
    total: Money
    installment_count: int
    description: str | None
    is_shared: bool = True
    owner_user_id: int | None = None
    owner_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    has_receipt: bool = False
    installments: list[InstallmentOut]
    splits: list[SplitOut] = Field(default_factory=list)


class SchedulePreviewIn(BaseModel):
    """Kaydetmeden önce gösterilen özet için girdi (§17)."""

    payment_method_id: int
    transaction_date: date
    amount: str = Field(min_length=1, max_length=32)
    installment_count: int = Field(
        default=MIN_INSTALLMENTS, ge=MIN_INSTALLMENTS, le=MAX_INSTALLMENTS
    )


class SchedulePreviewOut(BaseModel):
    total: Money
    installment_count: int
    installment_amount: Money
    first_statement_date: date | None
    first_due_date: date | None
    last_due_date: date | None
    is_credit_card: bool


class NamedTotalOut(BaseModel):
    id: int
    name: str
    emoji: str = ""
    total: Money
    transaction_count: int


class MonthlySpendingOut(BaseModel):
    year: int
    month: int
    total: Money
    transaction_count: int
    cash_total: Money
    card_total: Money
    by_user: list[NamedTotalOut]
    by_category: list[NamedTotalOut]
    largest_expense: ExpenseOut | None = None


class PersonalBudgetOut(BaseModel):
    user_id: int
    name: str
    year: int
    budget: Money | None = None
    spent: Money
    remaining: Money | None = None
    ratio: int
    is_exceeded: bool
    expense_count: int
    year_elapsed_ratio: int


class PersonalBudgetIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    amount: str | None = Field(default=None, max_length=32)
    """Boş bırakılırsa o yılın bütçesi kaldırılır."""


class StatementOut(BaseModel):
    payment_method_id: int
    payment_method_name: str
    statement_date: date
    due_date: date
    total: Money
    installment_count: int


class InstallmentPlanOut(BaseModel):
    expense_id: int
    public_id: str
    description: str | None
    category_name: str
    payment_method_name: str
    total: Money
    remaining: Money
    monthly: Money
    position: str


class ObligationOut(BaseModel):
    year: int
    month: int
    total: Money
    installment_count: int


class ObligationsOut(BaseModel):
    basis: str
    basis_label: str
    months: list[ObligationOut]


class PaymentMethodUpdateIn(BaseModel):
    """Kart ayarı düzenleme.

    `type` bilerek yer almaz: nakit bir yöntemi karta çevirmek, ona bağlı
    geçmiş harcamaların anlam değiştirmesi demek olurdu.

    Son ödeme günü ayrı bir alan değildir; ekstre tarihinden
    `due_offset_days` gün sonrası olarak hesaplanır.
    """

    name: str | None = Field(default=None, min_length=1, max_length=64)
    statement_day: int | None = Field(default=None, ge=1, le=31)
    due_offset_days: int | None = Field(default=None, ge=1, le=60)
    cutoff_inclusive: bool | None = None
    credit_limit_minor: int | None = Field(default=None, ge=0)
    owner_user_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class PaymentMethodCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str
    statement_day: int | None = Field(default=None, ge=1, le=31)
    due_offset_days: int = Field(default=10, ge=1, le=60)
    cutoff_inclusive: bool = True
    owner_user_id: int | None = None
    credit_limit_minor: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class CategoryCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    emoji: str = Field(default="", max_length=8)
    sort_order: int = 0
    monthly_budget_minor: int | None = Field(default=None, gt=0)
    group_name: str | None = Field(default=None, max_length=64)
    rollover: bool = False


class CategoryUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    emoji: str | None = Field(default=None, max_length=8)
    sort_order: int | None = None
    is_active: bool | None = None
    group_name: str | None = Field(default=None, max_length=64)
    """Boş metin grubu kaldırır."""
    rollover: bool | None = None
    monthly_budget_minor: int | None = Field(default=None, ge=0)
    """Sıfır verilirse hedef kaldırılır.

    `exclude_none` ile temizlenen bir gövdede `null` göndererek hedefi silmek
    mümkün olmadığı için sıfır bu anlamı üstlenir."""


class BudgetStatusOut(BaseModel):
    category_id: int
    name: str
    emoji: str
    budget: Money
    spent: Money
    remaining: Money
    ratio: int
    is_exceeded: bool
    carry_in: Money = Field(default_factory=lambda: Money.of(0))
    """Önceki aylardan devreden; aşım devrettiyse eksidir."""
    available: Money | None = None
    """Hedef ve devir birlikte: bu ay harcanabilecek tutar."""
    group_name: str | None = None
    rollover: bool = False


class TargetSuggestionOut(BaseModel):
    category_id: int
    name: str
    emoji: str
    group_name: str | None = None
    current: Money | None = None
    average: Money
    suggested: Money | None = None
    months: int


class TargetApplyItem(BaseModel):
    category_id: int
    monthly_budget_minor: int = Field(ge=0)
    """Sıfır hedefi kaldırır."""


class TargetApplyIn(BaseModel):
    items: list[TargetApplyItem] = Field(min_length=1, max_length=200)


class SearchResultOut(BaseModel):
    items: list[ExpenseOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool


class RecurringExpenseOut(BaseModel):
    """Sabit gider şablonu.

    Bu bir harcama değil, her ay hangi harcamanın oluşturulacağının tarifidir;
    tutar yalnızca varsayılandır ve değiştirilmesi geçmişi etkilemez.
    """

    id: int
    name: str
    category_id: int
    payment_method_id: int
    amount: Money
    day_of_month: int
    start_date: date
    notes: str | None = None
    is_active: bool


class RecurringExpenseCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    category_id: int
    payment_method_id: int
    amount_minor: int = Field(gt=0)
    day_of_month: int = Field(ge=1, le=31)
    start_date: date | None = None
    """Boş bırakılırsa bugünden başlar; geçmiş aylara kayıt üretilmez."""
    notes: str | None = Field(default=None, max_length=500)


class RecurringExpenseUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    category_id: int | None = None
    payment_method_id: int | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    notes: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class IncomeOut(BaseModel):
    id: int
    source: str
    amount: Money
    received_date: date
    notes: str | None = None


class IncomeCreateIn(BaseModel):
    amount_minor: int = Field(gt=0)
    received_date: date | None = None
    """Boş bırakılırsa bugün kabul edilir."""
    source: str = Field(default="Gelir", min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=500)


class CardUsageOut(BaseModel):
    """Kartın limit durumu. Limit girilmemişse oran ve kullanılabilir sıfırdır."""

    payment_method_id: int
    name: str
    credit_limit: Money | None = None
    outstanding: Money
    available: Money
    ratio: int
    is_over_limit: bool


class MonthlyPositionOut(BaseModel):
    """Ayın nakit durumu: ne girdi, ne çıkacak, ne kalır."""

    year: int
    month: int
    income: Money
    card_due: Money
    cash_spent: Money
    expected_recurring: Money
    outflow: Money
    remaining: Money


class RefundOut(BaseModel):
    """İade kaydı. Harcamanın taksit planı bundan etkilenmez."""

    id: int
    expense_id: int
    amount: Money
    refund_date: date
    statement_date: date | None = None
    due_date: date | None = None
    notes: str | None = None


class RefundCreateIn(BaseModel):
    amount_minor: int = Field(gt=0)
    refund_date: date | None = None
    """Boş bırakılırsa bugün kabul edilir."""
    notes: str | None = Field(default=None, max_length=500)


class TagTotalOut(BaseModel):
    """Bir etiketin toplamı.

    Etiket bir kategori değildir: aynı olayın farklı kategorilerdeki
    harcamalarını tek bir toplamda birleştirir.
    """

    tag: str
    total: Money
    transaction_count: int


class MonthForecastOut(BaseModel):
    """Ay sonu harcama tahmini ve dayanakları.

    Dayanaklar da döndürülür: tahmin bir kara kutu değildir, kullanıcı hangi
    sayıdan geldiğini görebilmelidir.
    """

    year: int
    month: int
    days_elapsed: int
    days_in_month: int
    spent_so_far: Money
    fixed: Money
    variable_forecast: Money
    variable_run_rate: Money
    variable_history: Money
    total: Money
    remaining: Money


class MonthComparisonOut(BaseModel):
    month: int
    this_year: Money
    last_year: Money
    change_percent: int | None = None
    """Geçen yıl aynı ayda kayıt yoksa oran hesaplanmaz."""


class YearComparisonOut(BaseModel):
    year: int
    months: list[MonthComparisonOut]
    this_year_total: Money
    last_year_total: Money




class SavingsGoalCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_minor: int = Field(gt=0)
    target_date: date
    saved_minor: int = Field(default=0, ge=0)
    """Hedef açılırken zaten kenarda duran tutar."""


class SavingsGoalUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    target_minor: int | None = Field(default=None, gt=0)
    target_date: date | None = None


class SavingsDepositIn(BaseModel):
    amount_minor: int
    """Eklenen tutar; eksi tutar birikimden para alındığını gösterir."""


class SavingsGoalOut(BaseModel):
    id: int
    name: str
    target: Money
    saved: Money
    remaining: Money
    target_date: date
    months_left: int
    monthly_required: Money
    ratio: int
    is_complete: bool
    is_overdue: bool


class SavingsOverviewOut(BaseModel):
    goals: list[SavingsGoalOut]
    monthly_required: Money
    """Tüm hedefler için bu ay ayrılması gereken toplam."""
    month_remaining: Money | None
    """Bu ayın nakit durumunda kalan; gelir girilmemişse boş."""
    covers: bool | None
    """Bu ayın kalanı hedeflere yetiyor mu; karşılaştırılamıyorsa boş."""


# ---------------------------------------------------------------------------
# Kurallar ve toplu işlemler
# ---------------------------------------------------------------------------


class RuleIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=120)
    match_type: str = "contains"
    set_category_id: int | None = None
    set_payment_method_id: int | None = None
    set_description: str | None = Field(default=None, max_length=120)
    sort_order: int = 0
    is_active: bool = True


class RuleUpdateIn(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=120)
    match_type: str | None = None
    set_category_id: int | None = None
    set_payment_method_id: int | None = None
    set_description: str | None = Field(default=None, max_length=120)
    sort_order: int | None = None
    is_active: bool | None = None
    clear: list[str] = Field(default_factory=list)
    """Boşaltılacak eylemler: `set_category_id`, `set_payment_method_id`,
    `set_description`. `null` göndermek gövdeden silindiği için ayrı yazılır."""


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    match_type: str
    set_category_id: int | None = None
    set_payment_method_id: int | None = None
    set_description: str | None = None
    sort_order: int
    is_active: bool


class RuleTestOut(BaseModel):
    category_id: int | None = None
    payment_method_id: int | None = None
    description: str | None = None
    rule_ids: list[int] = Field(default_factory=list)


class PreviousValuesOut(BaseModel):
    expense_id: int
    category_id: int
    description: str | None = None
    is_shared: bool
    owner_user_id: int | None = None


class BulkResultOut(BaseModel):
    changed: list[int]
    skipped: dict[int, str] = Field(default_factory=dict)
    previous: list[PreviousValuesOut] = Field(default_factory=list)
    """Değişiklikten önceki değerler; geri almak için aynen geri gönderilir."""


class BulkUpdateIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    category_id: int | None = None
    is_shared: bool | None = None
    owner_user_id: int | None = None
    add_tag: str | None = Field(default=None, max_length=40)
    remove_tag: str | None = Field(default=None, max_length=40)


class BulkIdsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class BulkRevertIn(BaseModel):
    items: list[PreviousValuesOut] = Field(min_length=1, max_length=5000)


class DescriptionGroupOut(BaseModel):
    key: str
    sample: str
    count: int
    total: Money


class MergeDescriptionsIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=50)
    target: str = Field(min_length=1, max_length=120)
    create_rule: bool = True


# ---------------------------------------------------------------------------
# İçe aktarma
# ---------------------------------------------------------------------------


class ColumnMappingIn(BaseModel):
    date_column: int = Field(ge=0)
    description_column: int = Field(ge=0)
    amount_column: int = Field(ge=0)
    first_row: int = Field(ge=0)


class ImportPreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)
    payment_method_id: int
    default_category_id: int | None = None
    sign: str = "auto"
    mapping: ColumnMappingIn | None = None


class ImportPreviewRowOut(BaseModel):
    index: int
    transaction_date: date | None
    description: str
    amount: Money
    category_id: int | None = None
    category_source: str | None = None
    payment_method_id: int | None = None
    installment_count: int
    installment_current: int | None = None
    duplicate_of: str | None = None
    skip_reason: str | None = None
    selected: bool
    note: str | None = None


class ImportPreviewOut(BaseModel):
    delimiter: str
    mapping: ColumnMappingIn
    sign: str
    columns: list[str]
    rows: list[ImportPreviewRowOut]


class ImportRowIn(BaseModel):
    transaction_date: date
    description: str | None = Field(default=None, max_length=500)
    amount_minor: int = Field(gt=0)
    category_id: int
    payment_method_id: int
    installment_count: int = Field(default=1, ge=MIN_INSTALLMENTS, le=MAX_INSTALLMENTS)
    is_shared: bool = True


class ImportCommitIn(BaseModel):
    rows: list[ImportRowIn] = Field(min_length=1, max_length=500)


class ImportCommitOut(BaseModel):
    created: int
    total: Money
    expense_ids: list[int]


# ---------------------------------------------------------------------------
# Mutabakat
# ---------------------------------------------------------------------------


class ReconcileSummaryOut(BaseModel):
    statement_date: date
    due_date: date
    ours_total: Money
    line_count: int
    cleared_count: int
    bank_total: Money | None = None
    difference: Money | None = None
    is_reconciled: bool
    changed_since: bool


class ReconcileLineOut(BaseModel):
    kind: str
    id: int
    expense_id: int
    public_id: str
    description: str | None = None
    transaction_date: date
    amount: Money
    installment_number: int | None = None
    installment_count: int | None = None
    cleared: bool


class ReconcileDetailOut(BaseModel):
    summary: ReconcileSummaryOut
    lines: list[ReconcileLineOut]
    cleared_total: Money
    note: str | None = None


class ReconcileClearIn(BaseModel):
    installment_ids: list[int] = Field(min_length=1, max_length=1000)
    cleared: bool


class ReconcileSaveIn(BaseModel):
    bank_total_minor: int
    note: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# Hesaplar
# ---------------------------------------------------------------------------


class AccountOut(BaseModel):
    id: int
    name: str
    kind: str
    is_active: bool
    notes: str | None = None
    balance: Money
    last_balance_date: date | None = None


class NetWorthPointOut(BaseModel):
    when: date
    assets: Money
    card_debt: Money
    net: Money


class AccountsOverviewOut(BaseModel):
    accounts: list[AccountOut]
    today: NetWorthPointOut
    history: list[NetWorthPointOut]


class AccountCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: str = "bank"
    opening_balance_minor: int | None = None
    opening_date: date | None = None
    notes: str | None = Field(default=None, max_length=200)


class AccountUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    kind: str | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=200)


class AccountEntryOut(BaseModel):
    id: int
    account_id: int
    entry_date: date
    kind: str
    amount: Money
    transfer_group: str | None = None
    payment_method_id: int | None = None
    note: str | None = None


class BalanceIn(BaseModel):
    balance_minor: int
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)


class AdjustmentIn(BaseModel):
    amount_minor: int
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)


class TransferIn(BaseModel):
    from_account_id: int
    to_account_id: int | None = None
    payment_method_id: int | None = None
    amount_minor: int = Field(gt=0)
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# Takvim ve ayrıntılı raporlar
# ---------------------------------------------------------------------------


class UpcomingEventOut(BaseModel):
    when: date
    kind: str
    title: str
    amount: Money | None = None
    detail: str | None = None
    payment_method_id: int | None = None


class MatrixRowOut(BaseModel):
    category_id: int
    name: str
    emoji: str
    group_name: str
    months: list[Money]
    total: Money


class CategoryMatrixOut(BaseModel):
    year: int
    rows: list[MatrixRowOut]
    month_totals: list[Money]
    total: Money


class FlowMonthOut(BaseModel):
    year: int
    month: int
    income: Money
    spending: Money
    net: Money


class DailySpendingOut(BaseModel):
    year: int
    month: int
    days: list[Money]
    total: Money


class FlowNodeOut(BaseModel):
    name: str
    amount: Money
    categories: list[NamedAmountOut] = Field(default_factory=list)


class NamedAmountOut(BaseModel):
    name: str
    amount: Money


class MoneyFlowOut(BaseModel):
    year: int
    month: int
    sources: list[FlowNodeOut]
    targets: list[FlowNodeOut]
    income: Money
    spending: Money
    remaining: Money


FlowNodeOut.model_rebuild()
