"""Home Assistant'a yayımlanacak sensör değerleri.

Eklenti bugüne kadar Home Assistant'a tek bir veri vermiyordu; yalnızca bir
panel açıyordu. Oysa veriler HA'ya girdiği anda bedavaya gelen üç şey var:
panoya kart koyabilmek, otomasyon yazabilmek (bütçe aşıldıysa ışığı kırmızı
yak) ve HA'nın kendi geçmiş grafiğini kullanabilmek.

Bu modül yalnızca **ne yayımlanacağını** hesaplar. Yayımlama işi
`app/ha_publisher.py` içindedir ve HTTP'ye bağlı olmadığı için buradaki her
şey doğrudan test edilebilir.

Durum değerleri lira cinsinden ondalıklı sayıdır: HA sayısal bir durumu
grafikleyebilmek için onu böyle bekler. Kuruş, hesabın yapıldığı yerde tam
sayı olarak kalır; yalnızca dışarı verilirken çevrilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from ..utils.time import local_today
from . import budgets, cards, cashflow, reports
from .finance.money import MINOR_UNITS_PER_MAJOR

DEVICE_CLASS_MONETARY = "monetary"
CURRENCY = "TRY"


def to_major(minor: int) -> float:
    """Kuruşu liraya çevirir. Yalnızca dışarı verirken kullanılır."""
    return round(minor / MINOR_UNITS_PER_MAJOR, 2)


@dataclass(frozen=True, slots=True)
class SensorState:
    """Tek bir HA sensörünün durumu."""

    entity_id: str
    state: float | str
    attributes: dict[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {"state": self.state, "attributes": self.attributes}


def _money_attributes(name: str, icon: str) -> dict[str, object]:
    return {
        "friendly_name": name,
        "unit_of_measurement": CURRENCY,
        "device_class": DEVICE_CLASS_MONETARY,
        "icon": icon,
    }


async def collect(session: AsyncSession, *, timezone: str) -> list[SensorState]:
    """Yayımlanacak bütün sensörleri üretir."""
    today = local_today(timezone)

    position = await cashflow.monthly_position(session, today=today)
    spending = await reports.monthly_spending(
        session, year=today.year, month=today.month
    )
    statements = await reports.upcoming_statements(session, since=today)
    budget_statuses = await budgets.monthly_status(
        session, year=today.year, month=today.month
    )
    card_usages = await cards.card_usage(session)

    return [
        _spending_sensor(spending),
        _income_sensor(position),
        _remaining_sensor(position),
        _next_statement_sensor(statements, today=today),
        _budget_sensor(budget_statuses),
        _card_sensor(card_usages),
    ]


def _spending_sensor(spending: reports.MonthlySpendingReport) -> SensorState:
    return SensorState(
        entity_id="sensor.butce_bu_ay_harcama",
        state=to_major(spending.total_minor),
        attributes={
            **_money_attributes("Bu ay harcama", "mdi:cart"),
            "islem_sayisi": spending.transaction_count,
            "nakit": to_major(spending.cash_total_minor),
            "kredi_karti": to_major(spending.card_total_minor),
            "kategoriler": {
                item.name: to_major(item.total_minor) for item in spending.by_category
            },
            "kisiler": {
                item.name: to_major(item.total_minor) for item in spending.by_user
            },
        },
    )


def _income_sensor(position: cashflow.MonthlyPosition) -> SensorState:
    return SensorState(
        entity_id="sensor.butce_bu_ay_gelir",
        state=to_major(position.income_minor),
        attributes=_money_attributes("Bu ay gelir", "mdi:cash-plus"),
    )


def _remaining_sensor(position: cashflow.MonthlyPosition) -> SensorState:
    """Ay sonunda kalan. Açık varsa negatif olur; otomasyon buna bakabilir."""
    return SensorState(
        entity_id="sensor.butce_kalan",
        state=to_major(position.remaining_minor),
        attributes={
            **_money_attributes("Ay sonunda kalan", "mdi:wallet"),
            "kart_odemeleri": to_major(position.card_due_minor),
            "nakit_harcama": to_major(position.cash_spent_minor),
            "bekleyen_sabit_gider": to_major(position.expected_recurring_minor),
            "toplam_cikis": to_major(position.outflow_minor),
        },
    )


def _next_statement_sensor(
    statements: list[reports.StatementSummary], *, today: date
) -> SensorState:
    """Sıradaki ekstre. Yaklaşan ekstre yoksa durum sıfırdır, boş değil.

    HA'da sayısal bir sensörün durumu bir kez metne dönerse geçmiş grafiği
    kopar; bu yüzden "yok" durumu da sayıyla, sıfırla anlatılır.
    """
    if not statements:
        return SensorState(
            entity_id="sensor.butce_yaklasan_ekstre",
            state=0.0,
            attributes=_money_attributes("Yaklaşan ekstre", "mdi:credit-card-clock"),
        )

    nearest = statements[0]
    return SensorState(
        entity_id="sensor.butce_yaklasan_ekstre",
        state=to_major(nearest.total_minor),
        attributes={
            **_money_attributes("Yaklaşan ekstre", "mdi:credit-card-clock"),
            "kart": nearest.payment_method_name,
            "ekstre_tarihi": nearest.statement_date.isoformat(),
            "son_odeme_tarihi": nearest.due_date.isoformat(),
            "kalan_gun": (nearest.due_date - today).days,
            "taksit_sayisi": nearest.installment_count,
        },
    )


def _budget_sensor(statuses: list[budgets.BudgetStatus]) -> SensorState:
    """Hedefi aşan kategori sayısı.

    Otomasyon için en kullanışlı biçim budur: `> 0` koşulu tek satırda
    yazılabilir ve hangi kategorilerin aştığı nitelikte durur.
    """
    exceeded = [status for status in statuses if status.is_exceeded]
    return SensorState(
        entity_id="sensor.butce_asilan_kategori",
        state=len(exceeded),
        attributes={
            "friendly_name": "Bütçesi aşılan kategori",
            "icon": "mdi:alert-circle-outline",
            "asilanlar": [status.name for status in exceeded],
            "durumlar": {
                status.name: status.ratio for status in statuses
            },
        },
    )


def _card_sensor(usages: list[cards.CardUsage]) -> SensorState:
    """Kartlara bağlanmış toplam borç.

    Durum toplam borçtur; kart kart kullanılabilir limit ise niteliklerde
    durur. Tek bir sayı, panoya konabilecek en anlamlı özettir.
    """
    with_limit = [usage for usage in usages if usage.has_limit]
    return SensorState(
        entity_id="sensor.butce_kart_borcu",
        state=to_major(sum(usage.outstanding_minor for usage in usages)),
        attributes={
            **_money_attributes("Kart borcu", "mdi:credit-card-outline"),
            "toplam_limit": to_major(
                sum(usage.credit_limit_minor for usage in with_limit)
            ),
            "kullanilabilir": to_major(
                sum(usage.available_minor for usage in with_limit)
            ),
            "kartlar": {
                usage.name: to_major(usage.outstanding_minor) for usage in usages
            },
            "doluluk_oranlari": {
                usage.name: usage.ratio for usage in with_limit
            },
        },
    )


__all__ = ["SensorState", "collect", "to_major"]