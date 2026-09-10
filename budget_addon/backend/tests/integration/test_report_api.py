"""Rapor uçlarının HTTP sözleşmesi.

Mini App'teki rapor ekranı bu uçlardan besleniyor ve her tutarı sunucudan
geldiği gibi gösteriyor. Bir alan adı değişir veya `Money` yapısı bozulursa
ekran sessizce boş kalırdı; bu testler sözleşmeyi yerinde tutar.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

HEADERS = {"X-Remote-User-Id": "70bbe879b6f145d9ba41e2ae8e2b81aa"}

MONEY_FIELDS = ("minor", "formatted")


def _is_money(value) -> bool:
    return isinstance(value, dict) and all(field in value for field in MONEY_FIELDS)


async def _record_expense(client, reference_data, amount="1.000"):
    response = await client.post(
        "/api/expenses",
        headers=HEADERS,
        json={
            "payment_method_id": reference_data["cash_id"],
            "category_id": reference_data["category_id"],
            "transaction_date": "2026-09-05",
            "amount": amount,
            "installment_count": 1,
            "description": "market #bodrum",
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_position_report_returns_money_objects(
    client, seeded_users, seeded_reference_data
):
    await _record_expense(client, seeded_reference_data)

    response = await client.get("/api/reports/position", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    for field in ("income", "card_due", "cash_spent", "outflow", "remaining"):
        assert _is_money(body[field]), field


async def test_forecast_report_shows_its_workings(
    client, seeded_users, seeded_reference_data
):
    response = await client.get("/api/reports/forecast", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["days_in_month"] >= 28
    assert _is_money(body["total"])
    assert _is_money(body["variable_run_rate"])


async def test_budget_report_is_empty_without_targets(
    client, seeded_users, seeded_reference_data
):
    response = await client.get("/api/reports/budgets", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == []


async def test_budget_report_lists_a_category_with_a_target(
    client, seeded_users, seeded_reference_data
):
    await client.patch(
        f"/api/categories/{seeded_reference_data['category_id']}",
        headers=HEADERS,
        json={"monthly_budget_minor": 50_000},
    )

    response = await client.get("/api/reports/budgets", headers=HEADERS)

    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Market"
    assert _is_money(body[0]["budget"])


async def test_card_report_lists_the_card(client, seeded_users, seeded_reference_data):
    response = await client.get("/api/reports/cards", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["credit_limit"] is None
    assert _is_money(body[0]["outstanding"])


async def test_settlement_report_names_both_sides(
    client, seeded_users, seeded_reference_data
):
    await _record_expense(client, seeded_reference_data)

    response = await client.get("/api/reports/settlement", headers=HEADERS)

    body = response.json()
    assert body["is_even"] is False
    assert body["creditor_name"] == "Aykut"
    assert body["debtor_name"] == "Aslıhan"
    assert _is_money(body["transfer"])


async def test_yearly_report_always_returns_twelve_months(
    client, seeded_users, seeded_reference_data
):
    response = await client.get("/api/reports/yearly?year=2026", headers=HEADERS)

    body = response.json()
    assert len(body["months"]) == 12
    assert body["months"][0]["month"] == 1


async def test_tag_report_groups_by_tag(client, seeded_users, seeded_reference_data):
    await _record_expense(client, seeded_reference_data)

    response = await client.get("/api/reports/tags", headers=HEADERS)

    body = response.json()
    assert body[0]["tag"] == "bodrum"
    assert body[0]["transaction_count"] == 1


async def test_expense_response_carries_the_shared_flag_and_tags(
    client, seeded_users, seeded_reference_data
):
    body = await _record_expense(client, seeded_reference_data)

    assert body["is_shared"] is True
    assert body["has_receipt"] is False


async def test_csv_export_is_downloadable(
    client, seeded_users, seeded_reference_data
):
    await _record_expense(client, seeded_reference_data)

    response = await client.get(
        "/api/export/expenses.csv?year=2026&month=9", headers=HEADERS
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "butce-harcama-2026-09.csv" in response.headers["content-disposition"]
    assert "1000,00" in response.text
