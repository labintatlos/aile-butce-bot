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
    """Mini App'in açılışta ihtiyaç duyduğu her şey tek istekte."""

    user: UserOut
    categories: list[CategoryOut]
    payment_methods: list[PaymentMethodOut]
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


class ExpenseUpdateIn(BaseModel):
    """Yalnızca gönderilen alanlar değiştirilir.

    `created_by_user_id` bilerek yer almaz: harcamanın sahibi doğrulanmış
    kimlikten gelir ve istemci tarafından değiştirilemez.
    """

    payment_method_id: int | None = None
    category_id: int | None = None
    transaction_date: date | None = None
    amount: str | None = Field(default=None, max_length=32)
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
    payment_method_name: str
    transaction_date: date
    total: Money
    installment_count: int
    description: str | None
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


class CategoryUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    emoji: str | None = Field(default=None, max_length=8)
    sort_order: int | None = None
    is_active: bool | None = None


class SearchResultOut(BaseModel):
    items: list[ExpenseOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
