/**
 * Ayrıntılı rapor sekmeleri: gruplu bütçe ve hedef önerisi, nakit akışı,
 * kategori × ay tablosu.
 *
 * Hiçbir tutar burada hesaplanmaz; grup toplamları bile sunucudan gelen
 * kuruşların toplanmasıdır ve yalnızca gösterim içindir.
 */

import { useMemo, useState } from "react";

import { api, type BudgetStatus, type CategoryMatrix, type TargetSuggestion } from "../api";
import { useSession } from "../context";
import { formatMinor, minorToInput, parseAmountToMinor, sanitiseAmount, shortMonthName, yearMonthOf } from "../format";
import { errorMessage, useAsync } from "../hooks";
import { FlowBars, MoneyFlowDiagram } from "./charts";
import { Icon } from "./icons";
import { BarRow } from "./reportParts";
import {
  Card,
  Empty,
  ErrorNote,
  Loading,
  Modal,
  MonthNav,
  Segmented,
  useToast,
  type YearMonth,
} from "./ui";

const UNGROUPED = "Diğer";

// ---------------------------------------------------------------------------
// Butce
// ---------------------------------------------------------------------------

function budgetMeta(item: BudgetStatus): string {
  const parts = [`%${item.ratio}`];
  parts.push(item.is_exceeded ? "hedef aşıldı" : `kalan ${item.remaining.formatted}`);
  if (item.carry_in.minor !== 0) {
    parts.push(
      item.carry_in.minor > 0
        ? `geçen aylardan +${item.carry_in.formatted} devreden`
        : `geçen aylardan ${item.carry_in.formatted} aşım devreden`,
    );
  }
  return parts.join(" · ");
}

export function BudgetPanel() {
  const { bootstrap, refresh } = useSession();
  const today = yearMonthOf(bootstrap.today);
  const [period, setPeriod] = useState<YearMonth>(today);
  const [suggesting, setSuggesting] = useState(false);
  const state = useAsync(() => api.budgets(period), [period.year, period.month]);

  const groups = useMemo(() => {
    const map = new Map<string, BudgetStatus[]>();
    for (const item of state.data ?? []) {
      const key = item.group_name || UNGROUPED;
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    return [...map.entries()].sort(([a], [b]) =>
      a === UNGROUPED ? 1 : b === UNGROUPED ? -1 : a.localeCompare(b, "tr"),
    );
  }, [state.data]);

  return (
    <div className="stack">
      <div className="row between wrap">
        <MonthNav value={period} onChange={setPeriod} max={today} />
        <button type="button" className="btn secondary sm" onClick={() => setSuggesting(true)}>
          <Icon name="wand" size={16} />
          Hedefleri geçmişten öner
        </button>
      </div>
      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}
      {state.data && state.data.length === 0 && (
        <Card>
          <Empty
            icon="chart"
            title="Bütçe hedefi tanımlı değil"
            text="Ayarlar → Kategoriler'den hedef girin ya da geçmiş harcamalarınızdan önerilsin."
          />
        </Card>
      )}
      {groups.length > 0 && (
        <div className="grid two">
          {groups.map(([name, items]) => {
            const spent = items.reduce((sum, item) => sum + item.spent.minor, 0);
            const available = items.reduce(
              (sum, item) => sum + (item.available?.minor ?? item.budget.minor),
              0,
            );
            return (
              <Card
                key={name}
                title={name}
                action={
                  <span className="muted small">
                    {formatMinor(spent)} / {formatMinor(available)}
                  </span>
                }
              >
                {items.map((item) => (
                  <BarRow
                    key={item.category_id}
                    label={`${item.emoji} ${item.name}${item.rollover ? " ↻" : ""}`}
                    value={`${item.spent.formatted} / ${(item.available ?? item.budget).formatted}`}
                    ratio={item.ratio}
                    tone={item.is_exceeded ? "danger" : item.ratio >= 80 ? "warning" : undefined}
                    meta={budgetMeta(item)}
                  />
                ))}
              </Card>
            );
          })}
        </div>
      )}
      {state.data && state.data.some((item) => item.rollover) && (
        <p className="muted small">↻ işaretli kategorilerde harcanmayan hedef sonraki aya devreder.</p>
      )}
      {suggesting && (
        <SuggestionModal
          onClose={() => setSuggesting(false)}
          onApplied={() => {
            setSuggesting(false);
            state.reload();
            refresh().catch(() => undefined);
          }}
        />
      )}
    </div>
  );
}

const PERIODS = [
  { value: "1", label: "Geçen ay" },
  { value: "3", label: "Son 3 ay" },
  { value: "6", label: "Son 6 ay" },
  { value: "12", label: "Son 12 ay" },
] as const;

function SuggestionModal({ onClose, onApplied }: { onClose: () => void; onApplied: () => void }) {
  const toast = useToast();
  const [months, setMonths] = useState<"1" | "3" | "6" | "12">("3");
  const state = useAsync(() => api.budgetSuggestions(Number(months)), [months]);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const valueOf = (item: TargetSuggestion) =>
    edits[item.category_id] ?? (item.suggested ? minorToInput(item.suggested.minor) : "");

  const apply = async () => {
    const items = (state.data ?? [])
      .filter((item) => chosen.has(item.category_id))
      .map((item) => ({
        category_id: item.category_id,
        monthly_budget_minor: parseAmountToMinor(valueOf(item)) ?? 0,
      }));
    if (items.length === 0) return;
    setBusy(true);
    try {
      await api.applyBudgets(items);
      toast(`${items.length} kategorinin hedefi güncellendi.`);
      onApplied();
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Hedefleri geçmişten öner"
      onClose={onClose}
      wide
      footer={
        <>
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy || chosen.size === 0}
            onClick={() => void apply()}
          >
            {busy ? "Kaydediliyor…" : `${chosen.size} hedefi uygula`}
          </button>
        </>
      }
    >
      <div className="stack">
        <p className="muted small">
          Öneri, seçilen dönemin tam aylarındaki ortalama net harcamadır ve 10 TL'ye yukarı
          yuvarlanır. İçinde bulunulan ay sayılmaz. Uygulamadan önce tutarları değiştirebilirsiniz.
        </p>
        <Segmented options={PERIODS} value={months} onChange={setMonths} />
        {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
        {!state.data && !state.error && <Loading />}
        {state.data && (
          <div className="table-wrap">
            <table className="table compact">
              <thead>
                <tr>
                  <th className="select-col">
                    <input
                      type="checkbox"
                      aria-label="Önerisi olanların tümü"
                      checked={
                        chosen.size > 0 &&
                        state.data.filter((item) => item.suggested).every((item) => chosen.has(item.category_id))
                      }
                      onChange={(event) =>
                        setChosen(
                          event.target.checked
                            ? new Set(state.data!.filter((item) => item.suggested).map((item) => item.category_id))
                            : new Set(),
                        )
                      }
                    />
                  </th>
                  <th>Kategori</th>
                  <th className="right">Ortalama</th>
                  <th className="right">Şu anki hedef</th>
                  <th className="right">Yeni hedef</th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((item) => (
                  <tr key={item.category_id}>
                    <td className="select-col">
                      <input
                        type="checkbox"
                        aria-label={`${item.name} seç`}
                        checked={chosen.has(item.category_id)}
                        onChange={() =>
                          setChosen((current) => {
                            const next = new Set(current);
                            if (next.has(item.category_id)) next.delete(item.category_id);
                            else next.add(item.category_id);
                            return next;
                          })
                        }
                      />
                    </td>
                    <td>
                      {item.emoji} {item.name}
                    </td>
                    <td className="right muted">{item.average.formatted}</td>
                    <td className="right">{item.current?.formatted ?? "—"}</td>
                    <td className="right">
                      <input
                        className="input"
                        style={{ maxWidth: 130, textAlign: "right" }}
                        inputMode="decimal"
                        placeholder="Hedef yok"
                        aria-label={`${item.name} yeni hedef`}
                        value={valueOf(item)}
                        onChange={(event) => {
                          const value = sanitiseAmount(event.target.value);
                          setEdits((current) => ({ ...current, [item.category_id]: value }));
                          setChosen((current) => new Set(current).add(item.category_id));
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Nakit akisi
// ---------------------------------------------------------------------------

const SPANS = [
  { value: "6", label: "6 ay" },
  { value: "12", label: "12 ay" },
  { value: "24", label: "24 ay" },
] as const;

export function FlowPanel() {
  const { bootstrap } = useSession();
  const today = yearMonthOf(bootstrap.today);
  const [span, setSpan] = useState<"6" | "12" | "24">("12");
  const [period, setPeriod] = useState<YearMonth>(today);
  const history = useAsync(() => api.cashflowHistory(Number(span)), [span]);
  const flow = useAsync(() => api.flow(period), [period.year, period.month]);

  return (
    <div className="stack">
      <Card
        title="Gelir ve harcama"
        action={<Segmented options={SPANS} value={span} onChange={setSpan} />}
      >
        <div className="legend mb-sm">
          <span>
            <i className="income" />
            Gelir
          </span>
          <span>
            <i className="spend" />
            Net harcama
          </span>
        </div>
        {history.data ? (
          <FlowBars months={history.data} />
        ) : history.error ? (
          <ErrorNote message={history.error} onRetry={history.reload} />
        ) : (
          <Loading />
        )}
      </Card>

      <Card
        title="Gelir nereye gitti?"
        action={<MonthNav value={period} onChange={setPeriod} max={today} />}
      >
        {flow.data ? (
          <MoneyFlowDiagram flow={flow.data} />
        ) : flow.error ? (
          <ErrorNote message={flow.error} onRetry={flow.reload} />
        ) : (
          <Loading />
        )}
        <p className="muted small mt">
          Harcamalar kategori gruplarına göre toplanır. Grubu olmayan kategoriler "Diğer" altında
          görünür.
        </p>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Kategori x ay
// ---------------------------------------------------------------------------

function shade(minor: number, peak: number): string {
  if (minor <= 0 || peak <= 0) return "cell";
  // Tepe degerin beste birinden kucuk hucreler boyanmaz; tablo okunur kalir.
  const step = Math.min(4, Math.floor((minor * 5) / peak));
  return step > 0 ? `cell s${step}` : "cell";
}

export function MatrixPanel() {
  const { bootstrap } = useSession();
  const currentYear = yearMonthOf(bootstrap.today).year;
  const [year, setYear] = useState(currentYear);
  const state = useAsync(() => api.categoryMatrix(year), [year]);

  return (
    <div className="stack">
      <div className="month-nav">
        <button type="button" className="icon-btn" aria-label="Önceki yıl" onClick={() => setYear((v) => v - 1)}>
          <Icon name="chevronLeft" />
        </button>
        <span>{year}</span>
        <button
          type="button"
          className="icon-btn"
          aria-label="Sonraki yıl"
          disabled={year >= currentYear}
          onClick={() => setYear((v) => v + 1)}
        >
          <Icon name="chevronRight" />
        </button>
      </div>
      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}
      {state.data && <MatrixTable matrix={state.data} />}
    </div>
  );
}

function MatrixTable({ matrix }: { matrix: CategoryMatrix }) {
  if (matrix.rows.length === 0) {
    return (
      <Card>
        <Empty icon="chart" title={`${matrix.year} yılında harcama kaydı yok`} />
      </Card>
    );
  }
  const peak = Math.max(0, ...matrix.rows.flatMap((row) => row.months.map((cell) => cell.minor)));
  let lastGroup = "";
  return (
    <Card flush title="Kategori × ay" action={<span className="muted small">Toplam {matrix.total.formatted}</span>}>
      <div className="table-wrap">
        <table className="table matrix">
          <thead>
            <tr>
              <th className="sticky">Kategori</th>
              {matrix.month_totals.map((_, index) => (
                <th key={index} className="right">
                  {shortMonthName(index + 1)}
                </th>
              ))}
              <th className="right">Yıl</th>
            </tr>
          </thead>
          <tbody>
            {matrix.rows.flatMap((row) => {
              const lines = [];
              if (row.group_name !== lastGroup) {
                lastGroup = row.group_name;
                lines.push(
                  <tr className="group-row" key={`g-${row.group_name}`}>
                    <td className="sticky" colSpan={14}>
                      {row.group_name}
                    </td>
                  </tr>,
                );
              }
              lines.push(
                <tr key={row.category_id}>
                  <td className="sticky">
                    {row.emoji} {row.name}
                  </td>
                  {row.months.map((cell, index) => (
                    <td
                      key={index}
                      className={shade(cell.minor, peak)}
                      title={`${row.name}, ${shortMonthName(index + 1)}: ${cell.formatted}`}
                    >
                      {cell.minor === 0 ? <span className="muted">—</span> : formatMinor(cell.minor).replace(" TL", "")}
                    </td>
                  ))}
                  <td className="cell strong">{row.total.formatted}</td>
                </tr>,
              );
              return lines;
            })}
          </tbody>
          <tfoot>
            <tr>
              <td className="sticky">Toplam</td>
              {matrix.month_totals.map((cell, index) => (
                <td key={index} className="cell">
                  {formatMinor(cell.minor).replace(" TL", "")}
                </td>
              ))}
              <td className="cell">{matrix.total.formatted}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="muted small card-pad">
        Tutarlar TL'dir; iadeler alındıkları aydan düşülür. Hücre ne kadar koyuysa harcama o kadar
        yüksektir.
      </p>
    </Card>
  );
}
