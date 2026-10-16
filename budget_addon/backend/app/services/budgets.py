"""Kategori bütçe hedefleri.

Harcamayı görmek ile ona bir ölçü koymak farklı şeylerdir. "Bu ay markete
3.200 TL verdim" tek başına iyi ya da kötü değildir; hedefin 4.000 TL olduğunu
bilmek onu anlamlı kılar.

Hedef bir **sınır değildir**: aşıldığında hiçbir kayıt engellenmez, yalnızca
haber verilir. Bütçe takibi harcamayı kısıtlamak için değil, görünür kılmak
içindir.

**Devreden bütçe.** Kategoride devir açıksa ay sonunda harcanmayan tutar bir
sonraki aya eklenir, aşılan tutar ise bir sonraki aydan düşülür. Devir,
açıldığı aydan (`Category.rollover_since`) itibaren birikir ve her geçmiş ay
için kategorinin **bugünkü** hedefi kullanılır: hedef değişiklikleri tarihçe
olarak saklanmaz, bu yüzden hedefi değiştiren kişi devri de yeni hedefe göre
görür.

Bu modül yalnızca durumu hesaplar. Uyarının ne zaman gönderileceğine
`services/scheduler.py`, nasıl yazılacağına `services/notification_texts.py` karar verir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category
from ..utils.time import month_bounds
from . import refunds
from .allocation import (
    refunded_by_category_month,
    spent_by_category,
    spent_by_category_month,
)
from .finance.dates import MONTHS_PER_YEAR

WARNING_RATIO = 80
"""Yüzde kaçta uyarı verileceği.

Aşıldıktan sonra haber vermek geç kalmış olurdu; ay ortasında hedefin dörtte
üçünü geçmiş olmak, kullanıcının davranışını hâlâ değiştirebileceği andır.
"""

EXCEEDED_RATIO = 100

BAR_SEGMENTS = 10


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    """Bir kategorinin bir aydaki hedef durumu."""

    category_id: int
    name: str
    emoji: str
    budget_minor: int
    spent_minor: int
    year: int
    month: int
    carry_in_minor: int = 0
    """Önceki aylardan devreden tutar; aşım devrettiyse negatiftir."""
    group_name: str | None = None
    rollover: bool = False

    @property
    def available_minor(self) -> int:
        """Bu ay harcanabilecek tutar: hedef ve devir birlikte."""
        return self.budget_minor + self.carry_in_minor

    @property
    def ratio(self) -> int:
        """Kullanılabilir tutarın yüzde kaçı harcanmış.

        Kullanılabilir tutar sıfır veya eksiyse taşma sayılır."""
        if self.available_minor <= 0:
            return EXCEEDED_RATIO
        return round(self.spent_minor * 100 / self.available_minor)

    @property
    def remaining_minor(self) -> int:
        """Kalan tutar. Hedef aşıldıysa negatif olmaz, sıfırlanır."""
        return max(self.available_minor - self.spent_minor, 0)

    @property
    def balance_minor(self) -> int:
        """Ay sonunda devredecek tutar; aşımda negatiftir."""
        return self.available_minor - self.spent_minor

    @property
    def overspend_minor(self) -> int:
        return max(self.spent_minor - self.available_minor, 0)

    @property
    def is_exceeded(self) -> bool:
        return self.spent_minor > self.available_minor

    @property
    def bar(self) -> str:
        """`▓▓▓▓▓▓▓░░░` — oranın metinle çizimi."""
        filled = min(round(self.ratio * BAR_SEGMENTS / 100), BAR_SEGMENTS)
        return "▓" * filled + "░" * (BAR_SEGMENTS - filled)


def _month_index(year: int, month: int) -> int:
    return year * MONTHS_PER_YEAR + (month - 1)


def _from_index(index: int) -> tuple[int, int]:
    year, month_index = divmod(index, MONTHS_PER_YEAR)
    return year, month_index + 1


async def _carry_in(
    session: AsyncSession, categories: list[Category], *, year: int, month: int
) -> dict[int, int]:
    """Devri açık kategorilerin bu aya getirdiği devir.

    Her geçmiş ay için `hedef - net harcama` toplanır. Devrin başladığı aydan
    önceki aylar ve bu ayın kendisi hesaba katılmaz.
    """
    starts = {
        category.id: _month_index(category.rollover_since.year, category.rollover_since.month)
        for category in categories
        if category.rollover and category.rollover_since is not None
    }
    rolling = [category for category in categories if category.id in starts]
    if not rolling:
        return {}
    current = _month_index(year, month)
    first = min(starts.values())
    if first >= current:
        return {}

    start, _ = month_bounds(*_from_index(first))
    _, end = month_bounds(*_from_index(current - 1))
    spent = await spent_by_category_month(session, start=start, end=end)
    refunded = await refunded_by_category_month(session, start=start, end=end)

    carries = {}
    for category in rolling:
        carry = 0
        for index in range(starts[category.id], current):
            key = (category.id, *_from_index(index))
            net = spent.get(key, 0) - refunded.get(key, 0)
            carry += (category.monthly_budget_minor or 0) - net
        carries[category.id] = carry
    return carries


async def monthly_status(
    session: AsyncSession, *, year: int, month: int
) -> list[BudgetStatus]:
    """Hedefi olan kategorilerin o aydaki durumunu verir.

    Hedefi olmayan kategoriler listeye girmez: onlar için söylenecek bir şey
    yoktur. Sıralama en çok zorlanandan başlar, çünkü kullanıcının önce
    görmesi gereken odur. Bölünmüş harcamanın her parçası kendi kategorisinin
    hedefinden düşer.
    """
    start, end = month_bounds(year, month)
    spent_by = await spent_by_category(session, start=start, end=end)

    # Iade edilen tutar kategoriyi rahatlatmalidir: geri alinan para
    # harcanmis sayilirsa hedef haksiz yere asilmis gorunur.
    refunded = await refunds.by_category_in_month(session, year=year, month=month)

    categories = list(
        (
            await session.scalars(
                select(Category).where(Category.monthly_budget_minor.is_not(None))
            )
        ).all()
    )
    carries = await _carry_in(session, categories, year=year, month=month)

    statuses = [
        BudgetStatus(
            category_id=category.id,
            name=category.name,
            emoji=category.emoji,
            budget_minor=category.monthly_budget_minor or 0,
            spent_minor=(
                spent_by.get(category.id, (0, 0))[0] - refunded.get(category.id, 0)
            ),
            year=year,
            month=month,
            carry_in_minor=carries.get(category.id, 0),
            group_name=category.group_name,
            rollover=category.rollover,
        )
        for category in categories
    ]
    return sorted(statuses, key=lambda status: status.ratio, reverse=True)


# ---------------------------------------------------------------------------
# Geçmişten hedef önerisi
# ---------------------------------------------------------------------------

SUGGESTION_STEP_MINOR = 1_000
"""Önerilen hedefler 10 TL'ye yukarı yuvarlanır: 2.873,40 TL yerine 2.880 TL
hem okunur hem de ortalamanın altına düşmez."""

SUGGESTION_PERIODS = (1, 3, 6, 12)


@dataclass(frozen=True, slots=True)
class TargetSuggestion:
    """Bir kategori için geçmiş harcamadan türetilen hedef."""

    category_id: int
    name: str
    emoji: str
    group_name: str | None
    current_minor: int | None
    average_minor: int
    suggested_minor: int | None
    months: int


def _round_up(value: int, step: int) -> int:
    return -(-value // step) * step


async def suggest_targets(
    session: AsyncSession, *, today: date, months: int = 3
) -> list[TargetSuggestion]:
    """Son `months` tam ayın ortalama net harcamasından hedef önerir.

    İçinde bulunulan ay sayılmaz: yarım ay ortalamayı aşağı çeker. Hiç
    harcaması olmayan kategoriye hedef önerilmez. Öneri yalnızca öneridir;
    uygulanana kadar hiçbir hedef değişmez.
    """
    if months not in SUGGESTION_PERIODS:
        raise ValueError("Geçersiz dönem")
    last = _month_index(today.year, today.month) - 1
    first = last - months + 1
    start, _ = month_bounds(*_from_index(first))
    _, end = month_bounds(*_from_index(last))
    spent = await spent_by_category_month(session, start=start, end=end)
    refunded = await refunded_by_category_month(session, start=start, end=end)

    totals: dict[int, int] = {}
    for (category_id, _year, _month), amount in spent.items():
        totals[category_id] = totals.get(category_id, 0) + amount
    for (category_id, _year, _month), amount in refunded.items():
        totals[category_id] = totals.get(category_id, 0) - amount

    categories = (
        await session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
    ).all()
    suggestions = []
    for category in categories:
        average = max(totals.get(category.id, 0), 0) // months
        suggestions.append(
            TargetSuggestion(
                category_id=category.id,
                name=category.name,
                emoji=category.emoji,
                group_name=category.group_name,
                current_minor=category.monthly_budget_minor,
                average_minor=average,
                suggested_minor=(
                    _round_up(average, SUGGESTION_STEP_MINOR) if average > 0 else None
                ),
                months=months,
            )
        )
    return suggestions


@dataclass(frozen=True, slots=True)
class BudgetAlert:
    """Gönderilmeye değer bir bütçe durumu."""

    status: BudgetStatus
    threshold: int

    @property
    def key(self) -> str:
        return (
            f"budget:{self.status.category_id}:"
            f"{self.status.year}-{self.status.month:02d}:{self.threshold}"
        )


def alerts_for(statuses: list[BudgetStatus]) -> list[BudgetAlert]:
    """Hangi kategorilerin eşiği geçtiğini söyler.

    Bir kategori aynı ay içinde iki kez haber verebilir: önce hedefinin
    %80'ine geldiğinde, sonra hedefi aştığında. Aynı eşik ikinci kez
    duyurulmaz; tekilleştirme `key` üzerinden yapılır.
    """
    alerts = []
    for status in statuses:
        if status.is_exceeded:
            alerts.append(BudgetAlert(status=status, threshold=EXCEEDED_RATIO))
        elif status.ratio >= WARNING_RATIO:
            alerts.append(BudgetAlert(status=status, threshold=WARNING_RATIO))
    return alerts
