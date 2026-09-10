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
    def of(cls, minor: int) -> "Money":
        return cls(minor=minor, formatted=format_try(minor))


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: str
    is_active: bool
    monthly_budget_minor: int | None = None


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
    """Harcama ortak mı. Varsayılan ortaktır; kişisel olan denkleştirmeye
    girmez."""
    owner_user_id: int | None = None
    """Kişisel harcamanın sahibi; verilirse harcama kişiseldir."""


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


class CategoryUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    emoji: str | None = Field(default=None, max_length=8)
    sort_order: int | None = None
    is_active: bool | None = None
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


class PersonBalanceOut(BaseModel):
    user_id: int
    name: str
    paid: Money
    share: Money
    balance: Money
    """Artı ise alacaklı, eksi ise borçlu."""


class SettlementOut(BaseModel):
    """Ortak giderlerin kişilere bölünmesi ve kalan denge."""

    year: int
    month: int
    shared_total: Money
    balances: list[PersonBalanceOut]
    is_even: bool
    transfer: Money
    creditor_name: str | None = None
    debtor_name: str | None = None
