"""Ay sonu harcama tahmini.

Ayın 10'unda "şu ana kadar 6.000 harcadım" demek yarım bir bilgidir; asıl
merak edilen bu gidişle ay sonunda ne olacağıdır.

Tahmin **tamamen deterministiktir**; hiçbir aşamada dil modeli veya öğrenen
bir model kullanılmaz. Formül açıktır ve mesajda kullanıcıya da anlatılır:

1. Sabit giderler ayrı tutulur. Onlar tahmin edilmez, **bilinir**: ayın
   şablonlarından toplanır. Kaydedilmiş olanı da, günü gelmemiş olanı da.
2. Geri kalan değişken harcama iki kaynaktan kestirilir: bu ayın günlük
   hızından ve önceki üç ayın ortalamasından.
3. İkisi ayın ne kadarının geçtiğine göre harmanlanır. Ayın başında geçmiş
   aylar ağır basar, çünkü üç günlük veriyle aya hükmedilemez; ay ilerledikçe
   bu ayın kendi hızı ağır basar.

Sabit giderin iki kez sayılmaması bu ayrımın asıl nedenidir: kira hem kayıtlı
harcamanın içinde olup hem de günlük hıza çarpılırsa tahmin şişer.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..utils.time import month_bounds
from . import recurring, refunds

HISTORY_MONTHS = 3
"""Kaç ay geriye bakılacağı.

Üç ay, mevsimsel bir dalgalanmayı yumuşatacak kadar uzun, geçen yılın alışkanlığını
bugüne taşımayacak kadar kısadır.
"""


@dataclass(frozen=True, slots=True)
class MonthForecast:
    """Bir ayın sonu için tahmin ve tahminin dayanakları."""

    year: int
    month: int
    days_elapsed: int
    days_in_month: int

    variable_so_far_minor: int
    variable_run_rate_minor: int
    variable_history_minor: int
    variable_forecast_minor: int
    fixed_minor: int
    recorded_fixed_minor: int

    @property
    def elapsed_ratio(self) -> float:
        return self.days_elapsed / self.days_in_month

    @property
    def spent_so_far_minor(self) -> int:
        """Bugüne kadar gerçekten harcanan (sabit giderler dâhil)."""
        return self.variable_so_far_minor + self.recorded_fixed_minor

    @property
    def total_minor(self) -> int:
        """Ay sonu için beklenen toplam harcama."""
        return self.variable_forecast_minor + self.fixed_minor

    @property
    def remaining_minor(self) -> int:
        """Ayın kalanında beklenen harcama. Beklenen aşıldıysa sıfırdır."""
        return max(self.total_minor - self.spent_so_far_minor, 0)

    @property
    def has_history(self) -> bool:
        return self.variable_history_minor > 0


def _previous_months(year: int, month: int, count: int) -> list[tuple[int, int]]:
    months = []
    for step in range(1, count + 1):
        total = (year * 12 + month - 1) - step
        months.append((total // 12, total % 12 + 1))
    return months


async def _variable_spending(
    session: AsyncSession, *, start: date, end: date
) -> int:
    """Sabit gider dışındaki net harcama.

    Sabit giderler ayrı hesaplandığı için buradan çıkarılır; iadeler de
    düşülür, çünkü geri alınan para harcanmış sayılmamalıdır.
    """
    spent = await session.scalar(
        select(func.coalesce(func.sum(Expense.total_amount_minor), 0)).where(
            Expense.deleted_at.is_(None),
            Expense.recurring_expense_id.is_(None),
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
    )
    year, month = start.year, start.month
    refunded = await refunds.by_category_in_month(session, year=year, month=month)
    return max(spent - sum(refunded.values()), 0)


async def _recorded_fixed(session: AsyncSession, *, start: date, end: date) -> int:
    """Bu ay şablondan üretilmiş harcamaların toplamı."""
    return await session.scalar(
        select(func.coalesce(func.sum(Expense.total_amount_minor), 0)).where(
            Expense.deleted_at.is_(None),
            Expense.recurring_expense_id.is_not(None),
            Expense.transaction_date >= start,
            Expense.transaction_date <= end,
        )
    )


async def _fixed_total(session: AsyncSession, *, today: date) -> int:
    """Ayın bütün sabit giderleri: kaydedilmiş olanlar ve günü gelmemiş olanlar.

    Şablonlardan toplanır, kayıtlardan değil: kullanıcı bir sabit gideri
    silmiş olsa bile ay sonunda o ödemeyi yapacaktır.
    """
    total = 0
    for template in await recurring.list_templates(session):
        when = recurring.scheduled_date(template, year=today.year, month=today.month)
        if when < template.start_date:
            continue
        total += template.amount_minor
    return total


async def month_forecast(session: AsyncSession, *, today: date) -> MonthForecast:
    """İçinde bulunulan ayın sonu için harcama tahmini."""
    start, end = month_bounds(today.year, today.month)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = max(today.day, 1)

    variable_so_far = await _variable_spending(session, start=start, end=today)
    recorded_fixed = await _recorded_fixed(session, start=start, end=end)
    fixed_total = await _fixed_total(session, today=today)

    run_rate = round(variable_so_far / days_elapsed * days_in_month)

    history_values = []
    for year, month in _previous_months(today.year, today.month, HISTORY_MONTHS):
        past_start, past_end = month_bounds(year, month)
        history_values.append(
            await _variable_spending(session, start=past_start, end=past_end)
        )
    recorded_history = [value for value in history_values if value > 0]
    history = (
        round(sum(recorded_history) / len(recorded_history)) if recorded_history else 0
    )

    ratio = days_elapsed / days_in_month
    if history:
        forecast = round(ratio * run_rate + (1 - ratio) * history)
    else:
        # Gecmis yoksa uydurmak yerine yalnizca bu ayin hizina bakilir.
        forecast = run_rate

    return MonthForecast(
        year=today.year,
        month=today.month,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        variable_so_far_minor=variable_so_far,
        variable_run_rate_minor=run_rate,
        variable_history_minor=history,
        variable_forecast_minor=max(forecast, variable_so_far),
        fixed_minor=fixed_total,
        recorded_fixed_minor=recorded_fixed,
    )
