"""Şartnamedeki kabul senaryolarının birebir karşılığı.

Kaynak: IMPLEMENTATION_PLAN.md bölüm 9 ve docs/TEST_SCENARIOS.md (A-*).
Bu testler şartnamede yazılı beklentileri sabitler; değişmeleri, sistemin
sözünden döndüğü anlamına gelir.
"""

from datetime import date

from app.services.finance.installments import build_schedule

ASLIHAN_KK1 = {"statement_day": 10, "due_day": 20}
THREE_THOUSAND_LIRA = 300_000  # kurus


def test_a1_specification_section_38_purchase_before_the_cutoff():
    schedule = build_schedule(
        total_minor=THREE_THOUSAND_LIRA,
        installment_count=3,
        transaction_date=date(2026, 9, 8),
        **ASLIHAN_KK1,
    )

    assert [line.amount_minor for line in schedule] == [100_000, 100_000, 100_000]
    assert [line.statement_date for line in schedule] == [
        date(2026, 9, 10),
        date(2026, 10, 10),
        date(2026, 11, 10),
    ]
    assert [line.due_date for line in schedule] == [
        date(2026, 9, 20),
        date(2026, 10, 20),
        date(2026, 11, 20),
    ]
    assert sum(line.amount_minor for line in schedule) == THREE_THOUSAND_LIRA


def test_a2_specification_section_39_purchase_after_the_cutoff():
    schedule = build_schedule(
        total_minor=THREE_THOUSAND_LIRA,
        installment_count=3,
        transaction_date=date(2026, 9, 11),
        **ASLIHAN_KK1,
    )

    assert [line.statement_date for line in schedule] == [
        date(2026, 10, 10),
        date(2026, 11, 10),
        date(2026, 12, 10),
    ]
    assert [line.due_date for line in schedule] == [
        date(2026, 10, 20),
        date(2026, 11, 20),
        date(2026, 12, 20),
    ]
    assert sum(line.amount_minor for line in schedule) == THREE_THOUSAND_LIRA


def test_a3_spending_and_cash_flow_are_different_numbers():
    """§40'ın finans motorunu ilgilendiren yarısı.

    12.000 TL / 12 taksit bir işlem, harcama raporunda tam tutarıyla; nakit
    akışı raporunda ise yalnızca o aya düşen taksitle görünür. Raporların
    kendisi veritabanı katmanıyla birlikte test edilir (I-R*).
    """
    television_total = 1_200_000
    schedule = build_schedule(
        total_minor=television_total,
        installment_count=12,
        transaction_date=date(2026, 9, 5),
        **ASLIHAN_KK1,
    )

    september_statement_load = sum(
        line.amount_minor
        for line in schedule
        if (line.statement_date.year, line.statement_date.month) == (2026, 9)
    )

    assert television_total == 1_200_000  # harcama raporu bu tutari kullanir
    assert september_statement_load == 100_000  # nakit akisi yalnizca ilk taksiti
    assert september_statement_load != television_total
