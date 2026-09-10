"""Home Assistant sensörleri: değerlerin üretilmesi ve yazılması.

Değerler lira cinsinden ondalıklı olmalıdır; HA sayısal bir durumu ancak öyle
grafikleyebilir. Kuruş yalnızca dışarı verilirken çevrilir, hesabın içinde tam
sayı kalır.
"""

from __future__ import annotations

from datetime import date

import pytest

from app import ha_publisher
from app.services import ha_state, income
from app.services.expenses import ExpenseInput, create_expense

pytestmark = pytest.mark.asyncio

TIMEZONE = "Europe/Istanbul"


async def _spend(session, user, fixtures, amount, *, method="cash", count=1):
    return await create_expense(
        session,
        user=user,
        data=ExpenseInput(
            payment_method_id=fixtures[method].id,
            category_id=fixtures["category"].id,
            transaction_date=date.today(),
            amount=amount,
            installment_count=count,
        ),
    )


def _by_id(sensors):
    return {sensor.entity_id: sensor for sensor in sensors}


async def test_minor_units_are_converted_to_lira():
    assert ha_state.to_major(1_248_075) == 12480.75
    assert ha_state.to_major(0) == 0.0


async def test_every_sensor_is_produced_even_on_an_empty_database(async_session):
    sensors = await ha_state.collect(async_session, timezone=TIMEZONE)

    assert set(_by_id(sensors)) == {
        "sensor.butce_bu_ay_harcama",
        "sensor.butce_bu_ay_gelir",
        "sensor.butce_kalan",
        "sensor.butce_yaklasan_ekstre",
        "sensor.butce_asilan_kategori",
        "sensor.butce_kart_borcu",
    }
    # Bos kurulumda bile durumlar sayisaldir; metne donen bir durum HA'daki
    # gecmis grafigini koparirdi.
    assert all(isinstance(sensor.state, (int, float)) for sensor in sensors)


async def test_spending_sensor_carries_the_breakdown(
    async_session, people, fixtures
):
    await _spend(async_session, people["aykut"], fixtures, "500")

    sensors = _by_id(await ha_state.collect(async_session, timezone=TIMEZONE))
    spending = sensors["sensor.butce_bu_ay_harcama"]

    assert spending.state == 500.0
    assert spending.attributes["nakit"] == 500.0
    assert spending.attributes["kategoriler"]["Market"] == 500.0
    assert spending.attributes["unit_of_measurement"] == "TRY"


async def test_remaining_sensor_goes_negative_when_there_is_a_shortfall(
    async_session, people, fixtures
):
    await income.create_income(
        async_session,
        user=people["aykut"],
        amount="1.000",
        received_date=date.today(),
        source="Maaş",
    )
    await _spend(async_session, people["aykut"], fixtures, "1.500")

    sensors = _by_id(await ha_state.collect(async_session, timezone=TIMEZONE))

    assert sensors["sensor.butce_kalan"].state == -500.0


async def test_budget_sensor_counts_exceeded_categories(
    async_session, people, fixtures
):
    fixtures["category"].monthly_budget_minor = 10_000
    await async_session.commit()
    await _spend(async_session, people["aykut"], fixtures, "500")

    sensors = _by_id(await ha_state.collect(async_session, timezone=TIMEZONE))
    alert = sensors["sensor.butce_asilan_kategori"]

    assert alert.state == 1
    assert alert.attributes["asilanlar"] == ["Market"]


# ---------------------------------------------------------------------------
# Yayımlama
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    """aiohttp istemcisi yerine geçen kayıt tutucu."""

    def __init__(self, status: int = 200):
        self.status = status
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, *, json, headers):
        self.calls.append((url, json))
        return FakeResponse(self.status)


def _settings(**overrides):
    from app.config import Settings

    defaults = dict(
        supervisor_token="test-token",
        _env_file=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _factory(async_session):
    class _Once:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Once()


async def test_every_sensor_is_posted_to_the_supervisor_api(async_session):
    client = FakeClient()

    written = await ha_publisher.publish_once(
        _settings(), _factory(async_session), client=client
    )

    assert written == 6
    urls = [url for url, _ in client.calls]
    assert urls[0] == (
        "http://supervisor/core/api/states/sensor.butce_bu_ay_harcama"
    )
    assert all("state" in payload for _, payload in client.calls)


async def test_nothing_is_posted_without_a_supervisor_token(async_session):
    client = FakeClient()

    written = await ha_publisher.publish_once(
        _settings(supervisor_token=""), _factory(async_session), client=client
    )

    assert written == 0
    assert client.calls == []


async def test_a_rejected_sensor_does_not_stop_the_others(async_session):
    """Home Assistant bir sensörü kabul etmezse diğerleri yine yazılır."""
    client = FakeClient(status=500)

    written = await ha_publisher.publish_once(
        _settings(), _factory(async_session), client=client
    )

    assert written == 0
    assert len(client.calls) == 6


async def test_card_sensor_reports_debt_and_available_limit(
    async_session, people, fixtures
):
    fixtures["card"].credit_limit_minor = 1_000_000
    await async_session.commit()
    await _spend(async_session, people["aykut"], fixtures, "1.200", method="card", count=12)

    sensors = _by_id(await ha_state.collect(async_session, timezone=TIMEZONE))
    card = sensors["sensor.butce_kart_borcu"]

    assert card.state == 1200.0
    assert card.attributes["kullanilabilir"] == 8800.0
    assert card.attributes["doluluk_oranlari"][fixtures["card"].name] == 12
