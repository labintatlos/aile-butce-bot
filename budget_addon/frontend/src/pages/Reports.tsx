/**
 * Raporlar: aylık harcama, kart yükü, yıllık karşılaştırma ve dışa aktarma.
 *
 * Grafikler için kütüphane kullanılmaz; oran çubuğu ve dikey sütun birkaç satır
 * CSS ile çizilir. Hiçbir tutar burada hesaplanmaz.
 */

import { useState } from "react";

import { api, type MonthlySpending, type ObligationBasis, type Obligations } from "../api";
import { Icon } from "../components/icons";
import {
  BarRow,
  BudgetBars,
  CardLimits,
  share,
  StatementList,
} from "../components/reportParts";
import {
  Card,
  Empty,
  ErrorNote,
  Loading,
  MonthNav,
  PageHeader,
  Segmented,
  Stat,
  Toggle,
  useToast,
  type YearMonth,
} from "../components/ui";
import { useSession } from "../context";
import { longDate, monthName, shortMonthName, yearMonthOf } from "../format";
import { errorMessage, useAsync } from "../hooks";

type Tab = "monthly" | "cards" | "yearly" | "export";

const TABS: readonly { value: Tab; label: string }[] = [
  { value: "monthly", label: "Aylık" },
  { value: "cards", label: "Kartlar ve taksitler" },
  { value: "yearly", label: "Yıllık" },
  { value: "export", label: "Dışa aktar" },
];

const BASIS_OPTIONS: readonly { value: ObligationBasis; label: string }[] = [
  { value: "statement", label: "Ekstreye göre" },
  { value: "due", label: "Son ödemeye göre" },
];

export function Reports() {
  const [tab, setTab] = useState<Tab>("monthly");
  return (
    <>
      <PageHeader title="Raporlar" subtitle="Harcamalar, kart yükü ve yıllık karşılaştırma" />
      <div className="tabs-row">
        <Segmented options={TABS} value={tab} onChange={setTab} />
      </div>
      {tab === "monthly" && <MonthlyReport />}
      {tab === "cards" && <CardsReport />}
      {tab === "yearly" && <YearlyReport />}
      {tab === "export" && <ExportPanel />}
    </>
  );
}

function MonthlyReport() {
  const { bootstrap } = useSession();
  const today = yearMonthOf(bootstrap.today);
  const [period, setPeriod] = useState<YearMonth>(today);
  const [owner, setOwner] = useState("all");
  const ownerOptions = [
    { value: "all", label: "Tümü" },
    { value: "shared", label: "Ortak" },
    ...bootstrap.people.map((person) => ({
      value: String(person.id),
      label: `${person.display_name} kişisel`,
    })),
  ];
  const state = useAsync(async () => {
    const [spending, budgets, tags] = await Promise.all([
      api.spending({ ...period, owner: owner === "all" ? undefined : owner }),
      api.budgets(period),
      api.tags(period),
    ]);
    return { spending, budgets, tags };
  }, [period.year, period.month, owner]);

  return (
    <div className="stack">
      <div className="row between wrap">
        <MonthNav value={period} onChange={setPeriod} max={today} />
        <Segmented options={ownerOptions} value={owner} onChange={setOwner} />
        {state.loading && state.data && <span className="spinner" />}
      </div>

      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}

      {state.data && (
        <>
          <SpendingStats spending={state.data.spending} />

          <div className="grid two">
            <Card title="Kategoriler">
              {state.data.spending.by_category.length === 0 ? (
                <Empty icon="chart" title="Bu ay harcama kaydı yok" />
              ) : (
                state.data.spending.by_category.map((item) => {
                  const ratio = share(item.total.minor, state.data!.spending.total.minor);
                  return (
                    <BarRow
                      key={item.id}
                      label={`${item.emoji} ${item.name}`}
                      value={item.total.formatted}
                      ratio={ratio}
                      meta={`%${Math.round(ratio)} · ${item.transaction_count} işlem`}
                    />
                  );
                })
              )}
            </Card>

            <Card title="Kişiler">
              {state.data.spending.by_user.length === 0 ? (
                <p className="muted">Kayıt yok.</p>
              ) : (
                state.data.spending.by_user.map((item) => (
                  <BarRow
                    key={item.id}
                    label={item.name}
                    value={item.total.formatted}
                    ratio={share(item.total.minor, state.data!.spending.total.minor)}
                    meta={`${item.transaction_count} işlem`}
                  />
                ))
              )}
            </Card>
          </div>

          <div className="grid two">
            {state.data.budgets.length > 0 && (
              <Card title="Bütçe hedefleri">
                <BudgetBars items={state.data.budgets} />
              </Card>
            )}
            {state.data.tags.length > 0 && (
              <Card title="Etiketler" flush>
                <div className="list">
                  {state.data.tags.map((tag) => (
                    <div className="list-item" key={tag.tag}>
                      <span className="list-icon">
                        <Icon name="tag" size={18} />
                      </span>
                      <span className="list-main">
                        <span className="list-title">#{tag.tag}</span>
                        <span className="list-sub">{tag.transaction_count} işlem</span>
                      </span>
                      <span className="list-end">
                        <span className="list-amount">{tag.total.formatted}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
            {state.data.spending.largest_expense && (
              <Card title="Ayın en büyük harcaması">
                <div className="detail-head">
                  <span className="list-icon large">
                    {state.data.spending.largest_expense.category.emoji || "🧾"}
                  </span>
                  <div className="list-main">
                    <div className="detail-amount">
                      {state.data.spending.largest_expense.total.formatted}
                    </div>
                    <div className="muted">
                      {state.data.spending.largest_expense.description ||
                        state.data.spending.largest_expense.category.name}{" "}
                      · {longDate(state.data.spending.largest_expense.transaction_date)}
                    </div>
                  </div>
                </div>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function SpendingStats({ spending }: { spending: MonthlySpending }) {
  return (
    <div className="grid stats">
      <Stat label="Toplam harcama" value={spending.total.formatted} icon="wallet" />
      <Stat label="İşlem sayısı" value={spending.transaction_count} icon="list" />
      <Stat label="Nakit" value={spending.cash_total.formatted} icon="wallet" />
      <Stat label="Kredi kartı" value={spending.card_total.formatted} icon="card" />
    </div>
  );
}

function CardsReport() {
  const [basis, setBasis] = useState<ObligationBasis>("statement");
  const base = useAsync(async () => {
    const [cards, statements, plans] = await Promise.all([
      api.cards(),
      api.statements(),
      api.installmentPlans(),
    ]);
    return { cards, statements, plans };
  }, []);
  const upcoming = useAsync(() => api.upcoming(12, basis), [basis]);

  if (!base.data) {
    return base.error ? <ErrorNote message={base.error} onRetry={base.reload} /> : <Loading />;
  }
  const { cards, statements, plans } = base.data;

  return (
    <div className="stack">
      <div className="grid two">
        <Card title="Kart limitleri">
          {cards.length === 0 ? (
            <Empty icon="card" title="Kredi kartı tanımlı değil" />
          ) : (
            <CardLimits items={cards} />
          )}
        </Card>
        <Card title="Yaklaşan ekstreler" flush>
          <StatementList items={statements} />
        </Card>
      </div>

      <Card
        title="Gelecek 12 ay kart yükü"
        action={<Segmented options={BASIS_OPTIONS} value={basis} onChange={setBasis} />}
      >
        {upcoming.data ? (
          <ObligationChart data={upcoming.data} />
        ) : upcoming.error ? (
          <ErrorNote message={upcoming.error} onRetry={upcoming.reload} />
        ) : (
          <Loading />
        )}
      </Card>

      <Card title="Aktif taksitler" flush>
        {plans.length === 0 ? (
          <Empty icon="card" title="Aktif taksit yok" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Harcama</th>
                  <th>Kart</th>
                  <th>Durum</th>
                  <th className="right">Aylık</th>
                  <th className="right">Kalan</th>
                  <th className="right">Toplam</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.expense_id}>
                    <td className="wrap">
                      <span className="strong">{plan.description || plan.category_name}</span>
                      <div className="muted small">
                        {plan.category_name} · {plan.public_id}
                      </div>
                    </td>
                    <td>{plan.payment_method_name}</td>
                    <td>
                      <span className="badge accent">{plan.position}</span>
                    </td>
                    <td className="right">{plan.monthly.formatted}</td>
                    <td className="right strong">{plan.remaining.formatted}</td>
                    <td className="right muted">{plan.total.formatted}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function ObligationChart({ data }: { data: Obligations }) {
  const peak = Math.max(1, ...data.months.map((month) => month.total.minor));
  const loaded = data.months.filter((month) => month.total.minor > 0);
  if (loaded.length === 0) {
    return <Empty icon="chart" title="Gelecek aylarda kart yükü görünmüyor" />;
  }
  return (
    <>
      <div className="chart">
        {data.months.map((month) => (
          <div
            className="chart-col"
            key={`${month.year}-${month.month}`}
            title={`${monthName(month.year, month.month)}: ${month.total.formatted}`}
          >
            <div className="chart-bars">
              <div
                className="chart-bar wide"
                style={{ height: `${(month.total.minor * 100) / peak}%` }}
              />
            </div>
            <span className="chart-label">{shortMonthName(month.month)}</span>
          </div>
        ))}
      </div>
      <div className="table-wrap mt">
        <table className="table compact">
          <tbody>
            {loaded.map((month) => (
              <tr key={`${month.year}-${month.month}`}>
                <td>{monthName(month.year, month.month)}</td>
                <td className="muted">{month.installment_count} taksit</td>
                <td className="right strong">{month.total.formatted}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small mt">{data.basis_label} gösteriliyor.</p>
    </>
  );
}

function YearlyReport() {
  const { bootstrap } = useSession();
  const currentYear = yearMonthOf(bootstrap.today).year;
  const [year, setYear] = useState(currentYear);
  const state = useAsync(() => api.yearly(year), [year]);

  return (
    <div className="stack">
      <div className="row">
        <div className="month-nav">
          <button
            type="button"
            className="icon-btn"
            aria-label="Önceki yıl"
            onClick={() => setYear((value) => value - 1)}
          >
            <Icon name="chevronLeft" />
          </button>
          <span>{year}</span>
          <button
            type="button"
            className="icon-btn"
            aria-label="Sonraki yıl"
            disabled={year >= currentYear}
            onClick={() => setYear((value) => value + 1)}
          >
            <Icon name="chevronRight" />
          </button>
        </div>
      </div>

      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}

      {state.data && (
        <>
          <div className="grid stats pair">
            <Stat label={`${state.data.year} toplamı`} value={state.data.this_year_total.formatted} icon="chart" />
            <Stat
              label={`${state.data.year - 1} toplamı`}
              value={state.data.last_year_total.formatted}
              icon="calendar"
            />
          </div>

          <Card
            title="Aylara göre harcama"
            action={
              <div className="legend">
                <span>
                  <i />
                  {state.data.year}
                </span>
                <span>
                  <i className="previous" />
                  {state.data.year - 1}
                </span>
              </div>
            }
          >
            <YearChart months={state.data.months} />
          </Card>

          <Card title="Karşılaştırma" flush>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Ay</th>
                    <th className="right">{state.data.year}</th>
                    <th className="right">{state.data.year - 1}</th>
                    <th className="right">Değişim</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.months.map((month) => (
                    <tr key={month.month}>
                      <td>{monthName(state.data!.year, month.month).split(" ")[0]}</td>
                      <td className="right strong">{month.this_year.formatted}</td>
                      <td className="right muted">{month.last_year.formatted}</td>
                      <td className="right">
                        {month.change_percent === null ? (
                          <span className="muted">—</span>
                        ) : (
                          <span className={month.change_percent > 0 ? "danger-text" : "success-text"}>
                            {month.change_percent > 0 ? "+" : ""}
                            {month.change_percent}%
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function YearChart({ months }: { months: { month: number; this_year: { minor: number; formatted: string }; last_year: { minor: number; formatted: string } }[] }) {
  const peak = Math.max(1, ...months.flatMap((month) => [month.this_year.minor, month.last_year.minor]));
  const recorded = months.some((month) => month.this_year.minor > 0 || month.last_year.minor > 0);
  if (!recorded) {
    return <Empty icon="chart" title="Bu iki yılda kayıt yok" />;
  }
  return (
    <div className="chart">
      {months.map((month) => (
        <div
          className="chart-col"
          key={month.month}
          title={`${shortMonthName(month.month)}: ${month.this_year.formatted} / ${month.last_year.formatted}`}
        >
          <div className="chart-bars">
            <div
              className="chart-bar previous"
              style={{ height: `${(month.last_year.minor * 100) / peak}%` }}
            />
            <div className="chart-bar" style={{ height: `${(month.this_year.minor * 100) / peak}%` }} />
          </div>
          <span className="chart-label">{shortMonthName(month.month)}</span>
        </div>
      ))}
    </div>
  );
}

function ExportPanel() {
  const { bootstrap } = useSession();
  const toast = useToast();
  const [period, setPeriod] = useState<YearMonth>(() => yearMonthOf(bootstrap.today));
  const [wholeYear, setWholeYear] = useState(false);
  const [busy, setBusy] = useState<"expenses" | "incomes" | null>(null);

  const run = async (kind: "expenses" | "incomes") => {
    setBusy(kind);
    try {
      // Ay verilmezse sunucu butun yili gonderir.
      const query = wholeYear ? { year: period.year } : period;
      const suffix = wholeYear
        ? String(period.year)
        : `${period.year}-${String(period.month).padStart(2, "0")}`;
      const name = kind === "expenses" ? "harcamalar" : "gelirler";
      await api.exportCsv(kind, query, `${name}-${suffix}.csv`);
      toast("Dosya indirildi.");
    } catch (cause: unknown) {
      toast(errorMessage(cause, "Dosya indirilemedi."), "danger");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="narrow">
      <Card title="CSV olarak dışa aktar">
        <div className="stack">
          <p className="muted">
            Seçilen dönemin kayıtları Excel veya Google E-Tablolar ile açılabilen bir CSV dosyası
            olarak indirilir.
          </p>
          <div>
            {wholeYear ? (
              <div className="month-nav">
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="Önceki yıl"
                  onClick={() => setPeriod({ ...period, year: period.year - 1 })}
                >
                  <Icon name="chevronLeft" />
                </button>
                <span>{period.year}</span>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="Sonraki yıl"
                  onClick={() => setPeriod({ ...period, year: period.year + 1 })}
                >
                  <Icon name="chevronRight" />
                </button>
              </div>
            ) : (
              <MonthNav value={period} onChange={setPeriod} />
            )}
          </div>
          <Toggle checked={wholeYear} onChange={setWholeYear} label="Bütün yılı indir" />
          <div className="form-actions start">
            <button
              type="button"
              className="btn primary"
              disabled={busy !== null}
              onClick={() => void run("expenses")}
            >
              <Icon name="download" size={16} />
              {busy === "expenses" ? "Hazırlanıyor…" : "Harcamaları indir"}
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={busy !== null}
              onClick={() => void run("incomes")}
            >
              <Icon name="download" size={16} />
              {busy === "incomes" ? "Hazırlanıyor…" : "Gelirleri indir"}
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
