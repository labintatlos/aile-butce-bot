/**
 * Harcamalar: arama, filtre, sayfalama (§25) ve toplu düzenleme.
 *
 * "Seç" açılınca satırlar işaretlenebilir; işaretlenenlere kategori, sahip,
 * etiket veya silme tek seferde uygulanır ve geri alınabilir.
 */

import { useEffect, useMemo, useState } from "react";

import { api, type SearchFilters } from "../api";
import { BulkBar } from "../components/BulkBar";
import { ExpenseDetail } from "../components/ExpenseDetail";
import { Icon } from "../components/icons";
import { ExpenseRow } from "../components/reportParts";
import { Card, Empty, ErrorNote, Field, Loading, PageHeader } from "../components/ui";
import { useSession } from "../context";
import { parseAmountToMinor, sanitiseAmount, shortDate } from "../format";
import { useAsync } from "../hooks";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

interface Filters {
  text: string;
  date_from: string;
  date_to: string;
  category_id: string;
  payment_method_id: string;
  created_by_user_id: string;
  min: string;
  max: string;
}

const EMPTY_FILTERS: Filters = {
  text: "",
  date_from: "",
  date_to: "",
  category_id: "",
  payment_method_id: "",
  created_by_user_id: "",
  min: "",
  max: "",
};

const optionalId = (value: string) => (value ? Number(value) : undefined);

export function Expenses() {
  const { bootstrap, users, navigate } = useSession();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [text, setText] = useState("");
  const [page, setPage] = useState(1);
  const [showFilters, setShowFilters] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());

  const toggle = (id: number) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const stopSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
  };
  const openOrToggle = (id: number) => (selecting ? toggle(id) : setOpenId(id));

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((current) => {
        if (current.text === text) return current;
        setPage(1);
        return { ...current, text };
      });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  const update = (key: keyof Filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  };

  const query = useMemo<SearchFilters>(
    () => ({
      text: filters.text.trim() || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      category_id: optionalId(filters.category_id),
      payment_method_id: optionalId(filters.payment_method_id),
      created_by_user_id: optionalId(filters.created_by_user_id),
      min_amount_minor: parseAmountToMinor(filters.min) ?? undefined,
      max_amount_minor: parseAmountToMinor(filters.max) ?? undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    [filters, page],
  );

  const state = useAsync(() => api.searchExpenses(query), [query]);

  const activeFilters = [
    filters.date_from,
    filters.date_to,
    filters.category_id,
    filters.payment_method_id,
    filters.created_by_user_id,
    filters.min,
    filters.max,
  ].filter(Boolean).length;

  const clear = () => {
    setFilters(EMPTY_FILTERS);
    setText("");
    setPage(1);
  };

  const result = state.data;

  return (
    <>
      <PageHeader
        title="Harcamalar"
        subtitle={result ? `${result.total} kayıt` : "Yükleniyor…"}
        actions={
          <button type="button" className="btn primary desktop-only" onClick={() => navigate("yeni")}>
            <Icon name="plus" size={18} />
            Harcama ekle
          </button>
        }
      />

      <Card flush>
        <div className="toolbar">
          <div className="search">
            <Icon name="search" size={18} />
            <input
              className="input"
              type="search"
              placeholder="Harcama ara"
              aria-label="Açıklama, etiket veya kayıt numarasıyla ara"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn secondary"
            aria-expanded={showFilters}
            onClick={() => setShowFilters((value) => !value)}
          >
            <Icon name="filter" size={16} />
            Filtreler
            {activeFilters > 0 && <span className="badge accent">{activeFilters}</span>}
          </button>
          {(activeFilters > 0 || text) && (
            <button type="button" className="btn ghost" onClick={clear}>
              Temizle
            </button>
          )}
          <button
            type="button"
            className={selecting ? "btn secondary" : "btn ghost"}
            aria-pressed={selecting}
            onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
          >
            <Icon name="check" size={16} />
            {selecting ? "Seçimi bitir" : "Seç"}
          </button>
        </div>

        {selecting && (
          <div className="card-pad">
            <BulkBar
              ids={[...selected]}
              onClear={() => setSelected(new Set())}
              onSelectAll={() =>
                setSelected(new Set((result?.items ?? []).map((expense) => expense.id)))
              }
              onDone={state.reload}
            />
          </div>
        )}

        {showFilters && (
          <div className="filters">
            <Field label="Başlangıç tarihi">
              <input
                className="input"
                type="date"
                value={filters.date_from}
                onChange={(event) => update("date_from", event.target.value)}
              />
            </Field>
            <Field label="Bitiş tarihi">
              <input
                className="input"
                type="date"
                value={filters.date_to}
                onChange={(event) => update("date_to", event.target.value)}
              />
            </Field>
            <Field label="Kategori">
              <select
                className="select"
                value={filters.category_id}
                onChange={(event) => update("category_id", event.target.value)}
              >
                <option value="">Tümü</option>
                {bootstrap.categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.emoji} {category.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Ödeme yöntemi">
              <select
                className="select"
                value={filters.payment_method_id}
                onChange={(event) => update("payment_method_id", event.target.value)}
              >
                <option value="">Tümü</option>
                {bootstrap.payment_methods.map((method) => (
                  <option key={method.id} value={method.id}>
                    {method.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Kaydeden">
              <select
                className="select"
                value={filters.created_by_user_id}
                onChange={(event) => update("created_by_user_id", event.target.value)}
              >
                <option value="">Herkes</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.display_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="En az (TL)">
              <input
                className="input"
                inputMode="decimal"
                value={filters.min}
                onChange={(event) => update("min", sanitiseAmount(event.target.value))}
              />
            </Field>
            <Field label="En çok (TL)">
              <input
                className="input"
                inputMode="decimal"
                value={filters.max}
                onChange={(event) => update("max", sanitiseAmount(event.target.value))}
              />
            </Field>
          </div>
        )}

        {state.error && (
          <div className="card-pad">
            <ErrorNote message={state.error} onRetry={state.reload} />
          </div>
        )}

        {!result ? (
          !state.error && <Loading />
        ) : result.items.length === 0 ? (
          <Empty
            icon="search"
            title="Harcama bulunamadı"
            text={
              activeFilters > 0 || filters.text
                ? "Filtreleri değiştirerek tekrar deneyin."
                : "İlk harcamanızı ekleyerek başlayın."
            }
          />
        ) : (
          <>
            <div className="table-wrap desktop-only">
              <table className="table">
                <thead>
                  <tr>
                    {selecting && <th className="select-col" aria-label="Seç" />}
                    <th>Tarih</th>
                    <th>Açıklama</th>
                    <th>Kategori</th>
                    <th>Ödeme</th>
                    <th>Kaydeden</th>
                    <th className="right">Tutar</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((expense) => (
                    <tr
                      key={expense.id}
                      className="clickable"
                      tabIndex={0}
                      aria-selected={selecting ? selected.has(expense.id) : undefined}
                      onClick={() => openOrToggle(expense.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") openOrToggle(expense.id);
                      }}
                    >
                      {selecting && (
                        <td className="select-col">
                          <input
                            type="checkbox"
                            aria-label={`${expense.public_id} seç`}
                            checked={selected.has(expense.id)}
                            onClick={(event) => event.stopPropagation()}
                            onChange={() => toggle(expense.id)}
                          />
                        </td>
                      )}
                      <td>{shortDate(expense.transaction_date)}</td>
                      <td className="wrap">
                        {expense.description || <span className="muted">—</span>}
                        {!expense.is_shared && (
                          <span className="badge ml">
                            {`${expense.owner_name ?? ""} kişisel`.trim()}
                          </span>
                        )}
                      </td>
                      <td>
                        {expense.splits.length > 1 ? (
                          <span title={expense.splits.map((part) => `${part.category_name} ${part.amount.formatted}`).join(" · ")}>
                            <Icon name="split" size={14} /> {expense.splits.length} kategori
                          </span>
                        ) : (
                          <>
                            {expense.category.emoji} {expense.category.name}
                          </>
                        )}
                      </td>
                      <td>
                        {expense.payment_method_name}
                        {expense.installment_count > 1 && (
                          <span className="badge accent ml">{expense.installment_count} taksit</span>
                        )}
                      </td>
                      <td>{expense.created_by}</td>
                      <td className="right strong">{expense.total.formatted}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="list mobile-only">
              {result.items.map((expense) =>
                selecting ? (
                  <div className="selectable-row" key={expense.id}>
                    <input
                      type="checkbox"
                      className="list-check"
                      aria-label={`${expense.public_id} seç`}
                      checked={selected.has(expense.id)}
                      onChange={() => toggle(expense.id)}
                    />
                    <ExpenseRow expense={expense} onOpen={() => toggle(expense.id)} />
                  </div>
                ) : (
                  <ExpenseRow key={expense.id} expense={expense} onOpen={() => setOpenId(expense.id)} />
                ),
              )}
            </div>

            {result.total_pages > 1 && (
              <div className="pager">
                <button
                  type="button"
                  className="btn secondary sm"
                  disabled={page <= 1}
                  onClick={() => setPage((value) => value - 1)}
                >
                  <Icon name="chevronLeft" size={16} />
                  Önceki
                </button>
                <span>
                  Sayfa {result.page} / {result.total_pages}
                </span>
                <button
                  type="button"
                  className="btn secondary sm"
                  disabled={!result.has_next}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Sonraki
                  <Icon name="chevronRight" size={16} />
                </button>
              </div>
            )}
          </>
        )}
      </Card>

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
