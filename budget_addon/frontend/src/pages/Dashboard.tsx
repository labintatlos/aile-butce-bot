/**
 * Özet: bu ayın durumu tek ekranda.
 */

import { useState } from "react";

import { api, type DashboardData, type NamedTotal } from "../api";
import { ExpenseDetail } from "../components/ExpenseDetail";
import { PersonalBudgetsCard } from "../components/PersonalBudgetsCard";
import { QuickEntry } from "../components/QuickEntry";
import { SavingsGoalsCard } from "../components/SavingsGoalsCard";
import { Icon } from "../components/icons";
import {
  BarRow,
  BudgetBars,
  CardLimits,
  ExpenseRow,
  share,
  StatementList,
} from "../components/reportParts";
import { Card, Empty, ErrorNote, Loading, Meter, PageHeader, Stat, useToast } from "../components/ui";
import { useSession } from "../context";
import { formatMinor, longDate, monthName } from "../format";
import { useAsync } from "../hooks";
import { UpcomingList } from "./Upcoming";

async function loadDashboardFallback(): Promise<DashboardData> {
  const [position, forecast, spending, budgets, cards, statements, recent, upcoming, personal_budgets, savings_goals] =
    await Promise.all([
      api.position(),
      api.forecast(),
      api.spending({}),
      api.budgets({}),
      api.cards(),
      api.statements(),
      api.searchExpenses({ page_size: 6 }),
      api.upcomingEvents(14).catch(() => []),
      api.personalBudgets().catch(() => []),
      api.savingsGoals().catch(() => ({
        goals: [],
        monthly_required: { minor: 0, formatted: "0,00 TL" },
        month_remaining: null,
        covers: null,
      })),
    ]);
  const shared_spending = await api.spending({ owner: "shared" }).catch(() => spending);
  return {
    position,
    forecast,
    spending,
    shared_spending,
    budgets,
    cards,
    statements,
    recent,
    upcoming,
    personal_budgets,
    savings_goals,
  };
}

export function Dashboard() {
  const { me, bootstrap, navigate, openQuickExpense } = useSession();
  const toast = useToast();
  const [openId, setOpenId] = useState<number | null>(null);

  const state = useAsync(
    () => api.dashboard().catch(() => loadDashboardFallback()),
    [],
    "dashboard",
  );

  const header = (
    <PageHeader
      title={`Merhaba, ${me.display_name}`}
      subtitle={`Bütçenize birlikte göz atalım · ${longDate(bootstrap.today)}`}
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

  const {
    position,
    forecast,
    spending,
    shared_spending,
    budgets,
    cards,
    statements,
    recent,
    upcoming,
    personal_budgets,
    savings_goals,
  } = state.data;
  const short = position.remaining.minor < 0;
  const monthProgress = share(forecast.days_elapsed, forecast.days_in_month);
  const topCategories = spending.by_category.slice(0, 6);
  const limitedCards = cards.filter((card) => card.credit_limit);

  return (
    <>
      {header}

      <QuickEntry
        inline
        onSaved={(expense) => {
          toast(`Harcama kaydedildi: ${expense.total.formatted}`, "success", {
            label: "Geri al",
            run: async () => {
              await api.deleteExpense(expense.id);
              state.reload();
            },
          });
          state.reload();
        }}
        onDraft={(draft) => {
          if (openQuickExpense) openQuickExpense(draft);
          else navigate("yeni");
        }}
      />

      <div className="grid main-side">
        <div className={short ? "hero is-negative" : "hero"}>
          <div className="hero-heading">
            <span className="hero-period">
              <Icon name="wallet" size={16} /> Aylık bütçeniz
            </span>
            <span className="hero-period">{monthName(position.year, position.month)}</span>
          </div>
          <div className="hero-label">{short ? "Bütçe açığı" : "Kalan bütçe"}</div>
          <div className="hero-value">{position.remaining.formatted}</div>
          <div className="hero-breakdown">
            <div>
              <span>Toplam gelir</span>
              <strong>{position.income.formatted}</strong>
            </div>
            <div>
              <span>Toplam çıkış</span>
              <strong>{position.outflow.formatted}</strong>
            </div>
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
        <button type="button" onClick={() => navigate("gelirler")}>
          <span className="quick-icon">
            <Icon name="income" />
          </span>
          <span>
            <strong>Gelirleri yönet</strong>
            <small>Bütçenizi güncel tutun</small>
          </span>
          <Icon name="chevronRight" size={18} />
        </button>
        <button type="button" onClick={() => navigate("sabit")}>
          <span className="quick-icon">
            <Icon name="repeat" />
          </span>
          <span>
            <strong>Sabit giderler</strong>
            <small>Düzenli ödemelerinizi takip edin</small>
          </span>
          <Icon name="chevronRight" size={18} />
        </button>
        <button type="button" onClick={() => navigate("raporlar")}>
          <span className="quick-icon">
            <Icon name="chart" />
          </span>
          <span>
            <strong>Raporları incele</strong>
            <small>Harcama dağılımınızı görüntüleyin</small>
          </span>
          <Icon name="chevronRight" size={18} />
        </button>
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
                <button
                  type="button"
                  className="btn primary"
                  onClick={() => (openQuickExpense ? openQuickExpense() : navigate("yeni"))}
                >
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
        <PersonalBudgetsCard
          year={position.year}
          initialData={personal_budgets}
          onChanged={state.reload}
        />

        <SavingsGoalsCard initialData={savings_goals} />

        {bootstrap.people.length >= 2 && (
          <SharedBalanceCard
            people={bootstrap.people}
            byUser={(shared_spending ?? spending).by_user}
            totalMinor={(shared_spending ?? spending).total.minor}
          />
        )}

        <Card
          title="Önümüzdeki 2 hafta"
          action={
            <button type="button" className="btn ghost sm" onClick={() => navigate("takvim")}>
              Tümü
              <Icon name="chevronRight" size={16} />
            </button>
          }
        >
          <UpcomingList events={upcoming.slice(0, 5)} today={bootstrap.today} />
        </Card>

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

function SharedBalanceCard({
  people,
  byUser,
  totalMinor,
}: {
  people: { id: number; display_name: string }[];
  byUser: NamedTotal[];
  totalMinor: number;
}) {
  const spentMap = new Map(byUser.map((u) => [u.id, u.total.minor]));
  const rows = people.map((p) => ({
    id: p.id,
    name: p.display_name,
    spent: spentMap.get(p.id) ?? 0,
  }));
  const fairShare = rows.length > 0 ? Math.round(totalMinor / rows.length) : 0;

  return (
    <Card title="Ortak gider dengesi">
      {totalMinor <= 0 ? (
        <p className="muted small">Bu ay ortak harcama kaydı yok.</p>
      ) : (
        <div className="stack">
          {rows.map((row) => {
            const diff = row.spent - fairShare;
            return (
              <div key={row.id}>
                <div className="row between">
                  <strong>{row.name}</strong>
                  <span className="num">{formatMinor(row.spent)}</span>
                </div>
                <Meter ratio={share(row.spent, totalMinor)} />
                <p className="muted small mt-xs">
                  {diff === 0
                    ? "Eşit"
                    : diff > 0
                      ? `Ortak ortalamadan +${formatMinor(diff)} fazla ödedi`
                      : `Ortak ortalamadan ${formatMinor(Math.abs(diff))} az ödedi`}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
