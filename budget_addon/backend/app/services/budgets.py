"""Kategori bütçe hedefleri.

Harcamayı görmek ile ona bir ölçü koymak farklı şeylerdir. "Bu ay markete
3.200 TL verdim" tek başına iyi ya da kötü değildir; hedefin 4.000 TL olduğunu
bilmek onu anlamlı kılar.

Hedef bir **sınır değildir**: aşıldığında hiçbir kayıt engellenmez, yalnızca
haber verilir. Bütçe takibi harcamayı kısıtlamak için değil, görünür kılmak
içindir.

Bu modül yalnızca durumu hesaplar. Uyarının ne zaman gönderileceğine
`app/bot/scheduler.py`, nasıl yazılacağına `app/bot/messages.py` karar verir.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category, Expense
from ..utils.time import month_bounds

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

    @property
    def ratio(self) -> int:
        """Hedefin yüzde kaçı harcanmış. Hedef sıfırsa taşma sayılır."""
        if self.budget_minor <= 0:
            return EXCEEDED_RATIO
        return round(self.spent_minor * 100 / self.budget_minor)

    @property
    def remaining_minor(self) -> int:
        """Kalan tutar. Hedef aşıldıysa negatif olmaz, sıfırlanır."""
        return max(self.budget_minor - self.spent_minor, 0)

    @property
    def overspend_minor(self) -> int:
        return max(self.spent_minor - self.budget_minor, 0)

    @property
    def is_exceeded(self) -> bool:
        return self.spent_minor > self.budget_minor

    @property
    def bar(self) -> str:
        """`▓▓▓▓▓▓▓░░░` — oranın metinle çizimi."""
        filled = min(round(self.ratio * BAR_SEGMENTS / 100), BAR_SEGMENTS)
        return "▓" * filled + "░" * (BAR_SEGMENTS - filled)


async def monthly_status(
    session: AsyncSession, *, year: int, month: int
) -> list[BudgetStatus]:
    """Hedefi olan kategorilerin o aydaki durumunu verir.

    Hedefi olmayan kategoriler listeye girmez: onlar için söylenecek bir şey
    yoktur. Sıralama en çok zorlanandan başlar, çünkü kullanıcının önce
    görmesi gereken odur.
    """
    start, end = month_bounds(year, month)

    spent_by_category = dict(
        (
            await session.execute(
                select(
                    Expense.category_id,
                    func.coalesce(func.sum(Expense.total_amount_minor), 0),
                )
                .where(
                    Expense.deleted_at.is_(None),
                    Expense.transaction_date >= start,
                    Expense.transaction_date <= end,
                )
                .group_by(Expense.category_id)
            )
        ).all()
    )

    categories = (
        await session.scalars(
            select(Category).where(Category.monthly_budget_minor.is_not(None))
        )
    ).all()

    statuses = [
        BudgetStatus(
            category_id=category.id,
            name=category.name,
            emoji=category.emoji,
            budget_minor=category.monthly_budget_minor or 0,
            spent_minor=spent_by_category.get(category.id, 0),
            year=year,
            month=month,
        )
        for category in categories
    ]
    return sorted(statuses, key=lambda status: status.ratio, reverse=True)


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
