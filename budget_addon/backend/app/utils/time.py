"""Yerel zaman yardımcıları.

"Bugün" kavramı tek bir yerden gelir. Sunucu UTC'de çalışsa bile kullanıcı
Türkiye'dedir; gece yarısına yakın saatlerde yanlış güne kaydetmemek için tüm
tarih varsayılanları yerel takvimden türetilir.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Istanbul"


def local_zone(timezone_name: str = DEFAULT_TIMEZONE) -> ZoneInfo:
    return ZoneInfo(timezone_name)


def local_now(timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    return datetime.now(local_zone(timezone_name))


def local_today(timezone_name: str = DEFAULT_TIMEZONE) -> date:
    return local_now(timezone_name).date()


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Ayın ilk ve son gününü kapalı aralık olarak verir."""
    import calendar

    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
