/**
 * Özet: bu ayın durumu tek ekranda.
 */

import { useState } from "react";

import { api } from "../api";
import { ExpenseDetail } from "../components/ExpenseDetail";
import { PersonalBudgetsCard } from "../components/PersonalBudgetsCard";
import { Icon } from "../components/icons";
import {
  BarRow,
  BudgetBars,
  CardLimits,
  ExpenseRow,
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
    const [position, forecast, spending, budgets, cards, statements, recent] =
      await Promise.all([
        api.position(),
        api.forecast(),
        api.spending({}),
        api.budgets({}),
        api.cards(),
        api.statements(),
        api.searchExpenses({ page_size: 6 }),
      ]);
    return { position, forecast, spending, budgets, cards, statements, recent };
  }, []);

  const header = (
    <PageHeader
      title={`Merhaba, ${me.display_name}`}
      subtitle={`Bütçenize birlikte göz atalım · ${longDate(bootstrap.today)}`}
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

  const { position, forecast, spending, budgets, cards, statements, recent } = state.data;
  const short = position.remaining.minor < 0;
  const monthProgress = share(forecast.days_elapsed, forecast.days_in_month);
  const topCategories = spending.by_category.slice(0, 6);
  const limitedCards = cards.filter((card) => card.credit_limit);

  return (
    <>
      {header}

      <div className="grid main-side">
        <div className={short ? "hero is-negative" : "hero"}>
          <div className="hero-heading">
            <span className="hero-period"><Icon name="wallet" size={16} /> Aylık bütçeniz</span>
            <span className="hero-period">{monthName(position.year, position.month)}</span>
          </div>
          <div className="hero-label">{short ? "Bütçe açığı" : "Kalan bütçe"}</div>
          <div className="hero-value">{position.remaining.formatted}</div>
          <div className="hero-breakdown">
            <div><span>Toplam gelir</span><strong>{position.income.formatted}</strong></div>
            <div><span>Toplam çıkış</span><strong>{position.outflow.formatted}</strong></div>
          </div>
          <Meter ratio={monthProgress} />
          <div className="hero-meta mt-sm">
            <span>
              {forecast.days_elapsed}/{forecast.days_in_month} gün geçti
            </span>
            <span>Tahmini ay sonu harcaması {forecast.total.formatted}</span>
          </div>
        </div>

        <div className="grid stats pair">
          <Stat
            label="Bu ayki harcama"
            value={spending.total.formatted}
            hint={`${spending.transaction_count} işlem`}
            icon="wallet"
          />
          <Stat label="Kart ödemeleri" value={position.card_due.formatted} icon="card" />
          <Stat label="Nakit harcama" value={position.cash_spent.formatted} icon="list" />
          <Stat
            label="Sabit gider"
            value={position.expected_recurring.formatted}
            hint="Bu ay beklenen"
            icon="repeat"
          />
        </div>
      </div>

      <div className="quick-actions" aria-label="Hızlı işlemler">
        <button type="button" onClick={() => navigate("gelirler")}><span className="quick-icon"><Icon name="income" /></span><span><strong>Gelirleri yönet</strong><small>Bütçenizi güncel tutun</small></span><Icon name="chevronRight" size={18} /></button>
        <button type="button" onClick={() => navigate("sabit")}><span className="quick-icon"><Icon name="repeat" /></span><span><strong>Sabit giderler</strong><small>Düzenli ödemelerinizi takip edin</small></span><Icon name="chevronRight" size={18} /></button>
        <button type="button" onClick={() => navigate("raporlar")}><span className="quick-icon"><Icon name="chart" /></span><span><strong>Raporları incele</strong><small>Harcama dağılımınızı görüntüleyin</small></span><Icon name="chevronRight" size={18} /></button>
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
        <PersonalBudgetsCard year={position.year} />

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
