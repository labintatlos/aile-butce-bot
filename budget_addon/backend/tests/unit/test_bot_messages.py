"""Bot mesajı biçimlendirme testleri.

Mesaj üreticileri saf fonksiyonlardır, bu yüzden Telegram olmadan sınanır.
Şartnamedeki §18 ve §42 (Türkçe biçim) burada sabitlenir.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.bot import messages
from app.bot.formatting import (
    expense_receipt,
    installment_label,
    long_date,
    money,
    month_name,
    short_date,
)
from app.services import reports


# ---------------------------------------------------------------------------
# §42: Turkce bicimler
# ---------------------------------------------------------------------------


def test_money_uses_turkish_formatting():
    assert money(1_245_075) == "12.450,75 TL"


def test_short_date_is_dotted():
    assert short_date(date(2026, 9, 2)) == "02.09.2026"


def test_long_date_is_readable_turkish():
    assert long_date(date(2026, 9, 2)) == "2 Eylül 2026"
    assert long_date(date(2026, 12, 31)) == "31 Aralık 2026"


def test_month_name_is_turkish():
    assert month_name(2026, 9) == "Eylül 2026"


@pytest.mark.parametrize("count, expected", [(1, "Peşin"), (3, "3 Taksit"), (12, "12 Taksit")])
def test_installment_label(count, expected):
    assert installment_label(count) == expected


# ---------------------------------------------------------------------------
# §18: kayit onay mesaji
# ---------------------------------------------------------------------------


def test_receipt_contains_every_field_the_specification_asks_for():
    text = expense_receipt(
        public_id="EXP-000184",
        category_name="Market",
        category_emoji="🛒",
        description="Migros alışverişi",
        total_minor=125_000,
        payment_method_name="Aslıhan Kredi Kartı 1",
        installment_count=3,
        first_statement_date=date(2026, 9, 10),
        is_credit_card=True,
    )

    assert "✅ Harcama kaydedildi" in text
    assert "🛒 Market" in text
    assert "Migros alışverişi" in text
    assert "1.250,00 TL" in text
    assert "Aslıhan Kredi Kartı 1" in text
    assert "3 Taksit" in text
    assert "10 Eylül 2026" in text
    assert "#EXP-000184" in text


def test_receipt_omits_the_statement_line_for_cash():
    text = expense_receipt(
        public_id="EXP-000001",
        category_name="Yakıt",
        category_emoji="⛽",
        description=None,
        total_minor=50_000,
        payment_method_name="Nakit",
        installment_count=1,
        first_statement_date=None,
        is_credit_card=False,
    )
    assert "İlk ekstre" not in text
    assert "Peşin" in text


# ---------------------------------------------------------------------------
# Rapor mesajlari
# ---------------------------------------------------------------------------


def make_monthly_report(**overrides) -> reports.MonthlySpendingReport:
    defaults = dict(
        year=2026,
        month=9,
        total_minor=1_350_000,
        transaction_count=3,
        cash_total_minor=50_000,
        card_total_minor=1_300_000,
        by_user=[
            reports.NamedTotal(id=1, name="Aykut", total_minor=1_200_000, transaction_count=1),
            reports.NamedTotal(id=2, name="Aslıhan", total_minor=150_000, transaction_count=2),
        ],
        by_category=[
            reports.NamedTotal(id=1, name="Market", emoji="🛒", total_minor=1_300_000),
        ],
        largest_expense=None,
    )
    defaults.update(overrides)
    return reports.MonthlySpendingReport(**defaults)


def test_monthly_report_shows_totals_and_people():
    text = messages.monthly_report(make_monthly_report())

    assert "Eylül 2026" in text
    assert "13.500,00 TL" in text
    assert "Aykut: 12.000,00 TL" in text
    assert "Aslıhan: 1.500,00 TL" in text
    assert "🛒 Market" in text


def test_monthly_report_warns_that_it_is_not_the_card_load():
    """Kullanıcı bu sayıyı kart borcuyla karıştırmamalıdır."""
    text = messages.monthly_report(make_monthly_report())
    assert "taksitli alışverişler tam" in text
    assert "Ekstreler" in text


def test_monthly_report_handles_an_empty_month():
    text = messages.monthly_report(
        make_monthly_report(
            total_minor=0, transaction_count=0, cash_total_minor=0,
            card_total_minor=0, by_user=[], by_category=[],
        )
    )
    assert messages.EMPTY_MONTH in text


def test_statements_report_lists_each_card():
    rows = [
        reports.StatementSummary(
            payment_method_id=1,
            payment_method_name="Aslıhan Kredi Kartı 1",
            statement_date=date(2026, 9, 10),
            due_date=date(2026, 9, 20),
            total_minor=1_243_000,
            installment_count=4,
        )
    ]
    text = messages.statements_report(rows)
    assert "Aslıhan Kredi Kartı 1" in text
    assert "10 Eylül 2026 ekstresi: 12.430,00 TL" in text
    assert "Son ödeme: 20 Eylül 2026" in text


def test_statements_report_handles_nothing_upcoming():
    assert messages.EMPTY_STATEMENTS in messages.statements_report([])


def test_installment_plan_report_shows_progress_and_remainder():
    plans = [
        reports.ActiveInstallmentPlan(
            expense_id=1,
            public_id="EXP-000012",
            description="Televizyon",
            category_name="Alışveriş",
            payment_method_name="Aykut Kredi Kartı 1",
            total_minor=1_200_000,
            installment_count=12,
            settled_count=4,
            remaining_minor=800_000,
        )
    ]
    text = messages.installment_plans_report(plans)
    assert "Televizyon" in text
    assert "Toplam: 12.000,00 TL" in text
    assert "Taksit: 4/12" in text
    assert "Kalan: 8.000,00 TL" in text
    assert "Aylık yaklaşık: 1.000,00 TL" in text


def test_obligations_report_states_which_basis_is_shown():
    """§23: arayüz hangi bakışı gösterdiğini açıkça yazmalıdır."""
    months = [
        reports.MonthlyObligation(year=2026, month=9, total_minor=3_542_000, installment_count=5),
        reports.MonthlyObligation(year=2026, month=10, total_minor=3_128_000, installment_count=4),
    ]

    statement_view = messages.obligations_report(months, basis_label="Ekstre Bazlı")
    due_view = messages.obligations_report(months, basis_label="Son Ödeme Bazlı")

    assert "Ekstre Bazlı" in statement_view
    assert "Son Ödeme Bazlı" in due_view
    assert "Eylül 2026: 35.420,00 TL" in statement_view
    assert "Toplam: 66.700,00 TL" in statement_view


def test_obligations_report_notes_that_cash_is_excluded():
    text = messages.obligations_report([], basis_label="Ekstre Bazlı")
    assert "nakit" in text.lower()


# ---------------------------------------------------------------------------
# Arama, ayarlar ve analiz mesajlari
# ---------------------------------------------------------------------------


class FakeCategory:
    def __init__(self, name, emoji=""):
        self.name = name
        self.emoji = emoji


class FakeMethod:
    def __init__(self, id, name, type, statement_day=None, due_day=None):
        self.id = id
        self.name = name
        self.type = type
        self.statement_day = statement_day
        self.due_day = due_day


def test_settings_overview_lists_card_numbers_and_days():
    text = messages.settings_overview(
        [
            FakeMethod(1, "Nakit", "cash"),
            FakeMethod(2, "Aslıhan Kredi Kartı 1", "credit_card", 26, 10),
        ],
        [FakeCategory("Market"), FakeCategory("Yakıt")],
    )

    assert "1. Nakit — nakit" in text
    assert "2. Aslıhan Kredi Kartı 1 — kesim 26, son ödeme 10" in text
    assert "/kart" in text


def test_settings_overview_warns_that_history_is_untouched():
    """Kullanıcı kart ayarını değiştirmenin geçmişi bozmadığını bilmelidir."""
    text = messages.settings_overview([FakeMethod(1, "Nakit", "cash")], [])
    assert "geçmiş harcamaların" in text.lower()
    assert "değiştirmez" in text


def test_search_results_reports_no_match():
    class EmptyPage:
        total = 0
        items = []
        has_next = False

    assert "sonuç bulunamadı" in messages.search_results(EmptyPage(), term="migros")


def test_analysis_shows_category_share_and_month_over_month():
    current = make_monthly_report(total_minor=1_000_000)
    previous = make_monthly_report(total_minor=800_000)

    text = messages.analysis_report(current, previous)

    assert "Analiz" in text
    assert "10.000,00 TL" in text
    assert "▲" in text  # artis
    assert "2.000,00 TL" in text  # fark
    assert "%25" in text


def test_analysis_handles_a_first_month_without_comparison():
    text = messages.analysis_report(make_monthly_report(), None)
    assert "Analiz" in text
    assert "Önceki aya göre" not in text


def test_analysis_handles_an_empty_month():
    empty = make_monthly_report(
        total_minor=0, transaction_count=0, by_user=[], by_category=[]
    )
    assert messages.EMPTY_MONTH in messages.analysis_report(empty, None)
