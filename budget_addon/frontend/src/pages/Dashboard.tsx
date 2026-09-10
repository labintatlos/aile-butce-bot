/**
 * Özet: bu ayın durumu tek ekranda.
 */

import { useState } from "react";

import { api } from "../api";
import { ExpenseDetail } from "../components/ExpenseDetail";
import { Icon } from "../components/icons";
import {
  BarRow,
  BudgetBars,
  CardLimits,
  ExpenseRow,
  SettlementView,
  share,
  StatementList,
} from "../components/reportParts";
import { Card, Empty, ErrorNote, Loading, Meter, PageHeader, Stat } from "../components/ui";
import { useSession } from "../context";
import { longDate, monthName } from "../format";
import { useAsync } from "../hooks";

export function Dashboard() {
  const { me, bootstrap, navigate } = useSession();
  const [openId, setOpenId] = useState<number | null>(null);

  const state = useAsync(async () => {
    const [position, forecast, spending, budgets, cards, statements, settlement, recent] =
      await Promise.all([
        api.position(),
        api.forecast(),
        api.spending({}),
        api.budgets({}),
        api.cards(),
        api.statements(),
        api.settlement({}),
        api.searchExpenses({ page_size: 6 }),
      ]);
    return { position, forecast, spending, budgets, cards, statements, settlement, recent };
  }, []);

  const header = (
    <PageHeader
      title={`Merhaba, ${me.display_name}`}
      subtitle={longDate(bootstrap.today)}
      actions={
        <button type="button" className="btn primary desktop-only" onClick={() => navigate("yeni")}>
          <Icon name="plus" size={18} />
          Harcama ekle
        </button>
      }
    />
  );

  if (!state.data) {
    return (
      <>
        {header}
        {state.error ? <ErrorNote message={state.error} onRetry={state.reload} /> : <Loading />}
      </>
    );
  }

  const { position, forecast, spending, budgets, cards, statements, settlement, recent } =
    state.data;
  const short = position.remaining.minor < 0;
  const monthProgress = share(forecast.days_elapsed, forecast.days_in_month);
  const topCategories = spending.by_category.slice(0, 6);
  const limitedCards = cards.filter((card) => card.credit_limit);

  return (
    <>
      {header}

      <div className="grid main-side">
        <div className="hero">
          <div className="hero-label">
            {monthName(position.year, position.month)} · {short ? "açık" : "kalan"}
          </div>
          <div className="hero-value">{position.remaining.formatted}</div>
          <div className="hero-meta">
            <span>Gelir {position.income.formatted}</span>
            <span>Toplam çıkış {position.outflow.formatted}</span>
          </div>
          <Meter ratio={monthProgress} />
          <div className="hero-meta mt-sm">
            <span>
              {forecast.days_elapsed}/{forecast.days_in_month} gün geçti
            </span>
            <span>Ay sonu tahmini {forecast.total.formatted}</span>
          </div>
        </div>

        <div className="grid stats pair">
          <Stat
            label="Bu ay harcama"
            value={spending.total.formatted}
            hint={`${spending.transaction_count} işlem`}
            icon="wallet"
          />
          <Stat label="Kart ödemeleri" value={position.card_due.formatted} icon="card" />
          <Stat label="Nakit harcama" value={position.cash_spent.formatted} icon="list" />
          <Stat
            label="Sabit gider"
            value={position.expected_recurring.formatted}
            hint="Bu ay bekleyen"
            icon="repeat"
          />
        </div>
      </div>

      <div className="grid two">
        <Card
          title="Son harcamalar"
          flush
          action={
            <button type="button" className="btn ghost sm" onClick={() => navigate("harcamalar")}>
              Tümü
              <Icon name="chevronRight" size={16} />
            </button>
          }
        >
          {recent.items.length === 0 ? (
            <Empty
              title="Henüz harcama yok"
              text="İlk harcamanızı ekleyerek başlayın."
              action={
                <button type="button" className="btn primary" onClick={() => navigate("yeni")}>
                  Harcama ekle
                </button>
              }
            />
          ) : (
            <div className="list">
              {recent.items.map((expense) => (
                <ExpenseRow key={expense.id} expense={expense} onOpen={() => setOpenId(expense.id)} />
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Kategoriler"
          action={
            <button type="button" className="btn ghost sm" onClick={() => navigate("raporlar")}>
              Rapor
              <Icon name="chevronRight" size={16} />
            </button>
          }
        >
          {topCategories.length === 0 ? (
            <Empty icon="chart" title="Bu ay harcama kaydı yok" />
          ) : (
            topCategories.map((item) => (
              <BarRow
                key={item.id}
                label={`${item.emoji} ${item.name}`}
                value={item.total.formatted}
                ratio={share(item.total.minor, spending.total.minor)}
                meta={`${item.transaction_count} işlem`}
              />
            ))
          )}
        </Card>
      </div>

      <div className="grid three">
        <Card title="Yaklaşan ekstreler" flush>
          <StatementList items={statements} limit={4} />
        </Card>

        {budgets.length > 0 && (
          <Card title="Bütçe hedefleri">
            <BudgetBars items={budgets} />
          </Card>
        )}

        {limitedCards.length > 0 && (
          <Card title="Kart limitleri">
            <CardLimits items={limitedCards} />
          </Card>
        )}

        <Card title="Ortak gider denkleştirmesi">
          <SettlementView settlement={settlement} />
        </Card>
      </div>

      {openId !== null && (
        <ExpenseDetail
          expenseId={openId}
          onClose={() => setOpenId(null)}
          onChanged={state.reload}
        />
      )}
    </>
  );
}
