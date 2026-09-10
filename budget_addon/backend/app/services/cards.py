"""Kart limiti ve kullanılabilir bakiye.

Kart limiti veritabanında baştan beri duruyordu ama hiçbir yerde
kullanılmıyordu. Oysa taksitli alışverişte asıl sıkıştıran şey ekstre tutarı
değil, limitin ne kadarının bağlandığıdır: 12 taksitli bir alışverişin tamamı
limitten düşer, ekstreye ise ayda bir taksiti gelir.

**Borç** burada henüz ödenmemiş taksitlerin toplamıdır. Ödenmiş olarak
işaretlenen taksit limiti serbest bırakır; iptal edilen de öyle. Tarih
sınırlaması yoktur: gelecek yıla sarkan bir taksit de bugünden limiti
bağlamıştır.

Limit girilmemiş kartlar hiçbir uyarı üretmez ve oran hesaplanmaz; sistem
bilmediği bir sayı hakkında yorum yapmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.installment import STATUS_SCHEDULED, ExpenseInstallment
from ..models.payment_method import TYPE_CREDIT_CARD, PaymentMethod

NEAR_LIMIT_RATIO = 90
"""Yüzde kaçta uyarı verileceği.

Limitin tamamı dolduğunda haber vermek işe yaramaz: o noktada kart zaten
çalışmaz. Onda dokuzu bağlandığında haber vermek, kullanıcının bir sonraki
alışverişini başka bir karta kaydırabileceği andır.
"""

FULL_RATIO = 100

BAR_SEGMENTS = 10


@dataclass(frozen=True, slots=True)
class CardUsage:
    """Bir kredi kartının limit durumu."""

    payment_method_id: int
    name: str
    credit_limit_minor: int | None
    outstanding_minor: int

    @property
    def has_limit(self) -> bool:
        return self.credit_limit_minor is not None and self.credit_limit_minor > 0

    @property
    def available_minor(self) -> int:
        """Kullanılabilir limit. Limit aşıldıysa sıfırlanır, negatife inmez."""
        if not self.has_limit:
            return 0
        return max(self.credit_limit_minor - self.outstanding_minor, 0)

    @property
    def ratio(self) -> int:
        """Limitin yüzde kaçı bağlanmış. Limit girilmemişse sıfır."""
        if not self.has_limit:
            return 0
        return round(self.outstanding_minor * 100 / self.credit_limit_minor)

    @property
    def is_over_limit(self) -> bool:
        return self.has_limit and self.outstanding_minor > self.credit_limit_minor

    @property
    def bar(self) -> str:
        """`▓▓▓▓▓▓▓░░░` — oranın metinle çizimi."""
        filled = min(round(self.ratio * BAR_SEGMENTS / 100), BAR_SEGMENTS)
        return "▓" * filled + "░" * (BAR_SEGMENTS - filled)


async def card_usage(session: AsyncSession) -> list[CardUsage]:
    """Aktif kredi kartlarının borç ve limit durumunu verir.

    Sıralama en çok dolu karttan başlar; kullanıcının önce görmesi gereken
    odur. Limiti olmayan kartlar listeye girer ama oranları sıfırdır.
    """
    outstanding = dict(
        (
            await session.execute(
                select(
                    Expense.payment_method_id,
                    func.coalesce(func.sum(ExpenseInstallment.amount_minor), 0),
                )
                .join(Expense, ExpenseInstallment.expense_id == Expense.id)
                .where(
                    Expense.deleted_at.is_(None),
                    Expense.payment_method_type_snapshot == TYPE_CREDIT_CARD,
                    ExpenseInstallment.status == STATUS_SCHEDULED,
                )
                .group_by(Expense.payment_method_id)
            )
        ).all()
    )

    cards = (
        await session.scalars(
            select(PaymentMethod)
            .where(
                PaymentMethod.type == TYPE_CREDIT_CARD,
                PaymentMethod.is_active.is_(True),
            )
            .order_by(PaymentMethod.name)
        )
    ).all()

    usages = [
        CardUsage(
            payment_method_id=card.id,
            name=card.name,
            credit_limit_minor=card.credit_limit_minor,
            outstanding_minor=outstanding.get(card.id, 0),
        )
        for card in cards
    ]
    return sorted(usages, key=lambda usage: usage.ratio, reverse=True)


@dataclass(frozen=True, slots=True)
class CardLimitAlert:
    """Limiti dolmaya yaklaşmış bir kart."""

    usage: CardUsage
    threshold: int
    year: int
    month: int

    @property
    def key(self) -> str:
        return (
            f"card_limit:{self.usage.payment_method_id}:"
            f"{self.year}-{self.month:02d}:{self.threshold}"
        )


def alerts_for(
    usages: list[CardUsage], *, year: int, month: int
) -> list[CardLimitAlert]:
    """Hangi kartların eşiği geçtiğini söyler.

    Bütçe uyarılarıyla aynı mantık: bir kart ayda en fazla iki kez haber
    verir, önce limitinin %90'ına geldiğinde, sonra limiti aştığında.
    """
    alerts = []
    for usage in usages:
        if not usage.has_limit:
            continue
        if usage.is_over_limit:
            alerts.append(
                CardLimitAlert(
                    usage=usage, threshold=FULL_RATIO, year=year, month=month
                )
            )
        elif usage.ratio >= NEAR_LIMIT_RATIO:
            alerts.append(
                CardLimitAlert(
                    usage=usage, threshold=NEAR_LIMIT_RATIO, year=year, month=month
                )
            )
    return alerts
