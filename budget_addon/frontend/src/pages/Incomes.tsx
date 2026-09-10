/**
 * Gelirler: ay ay listeleme, ekleme ve silme.
 */

import { useState, type FormEvent } from "react";

import { api, type Income } from "../api";
import { Icon } from "../components/icons";
import {
  Card,
  ConfirmButton,
  Empty,
  ErrorNote,
  Field,
  Loading,
  Modal,
  MonthNav,
  PageHeader,
  Stat,
  useToast,
  type YearMonth,
} from "../components/ui";
import { useSession } from "../context";
import { formatMinor, longDate, monthName, parseAmountToMinor, sanitiseAmount, yearMonthOf } from "../format";
import { errorMessage, useAsync } from "../hooks";

const SOURCE_SUGGESTIONS = ["Maaş", "Ek gelir", "Kira geliri", "Prim"];

export function Incomes() {
  const { bootstrap } = useSession();
  const toast = useToast();
  const [period, setPeriod] = useState<YearMonth>(() => yearMonthOf(bootstrap.today));
  const [adding, setAdding] = useState(false);
  const state = useAsync(() => api.incomes(period), [period.year, period.month]);

  const items = state.data ?? [];
  const totalMinor = items.reduce((sum, item) => sum + item.amount.minor, 0);

  return (
    <>
      <PageHeader
        title="Gelirler"
        subtitle="Ay sonu kalan hesabı bu kayıtlara göre yapılır."
        actions={
          <button type="button" className="btn primary" onClick={() => setAdding(true)}>
            <Icon name="plus" size={18} />
            Gelir ekle
          </button>
        }
      />

      <div className="stack">
        <div className="row between wrap">
          <MonthNav value={period} onChange={setPeriod} />
        </div>

        <div className="grid stats pair">
          <Stat label={`${monthName(period.year, period.month)} geliri`} value={formatMinor(totalMinor)} icon="income" tone="success" />
          <Stat label="Kayıt" value={items.length} icon="list" />
        </div>

        <Card title="Kayıtlar" flush>
          {state.error && (
            <div className="card-pad">
              <ErrorNote message={state.error} onRetry={state.reload} />
            </div>
          )}
          {!state.data && !state.error && <Loading />}
          {state.data && items.length === 0 && (
            <Empty
              icon="income"
              title="Bu ay gelir kaydı yok"
              action={
                <button type="button" className="btn secondary" onClick={() => setAdding(true)}>
                  Gelir ekle
                </button>
              }
            />
          )}
          {items.length > 0 && (
            <div className="list">
              {items.map((item) => (
                <div className="list-item" key={item.id}>
                  <span className="list-icon success-text">
                    <Icon name="income" size={18} />
                  </span>
                  <span className="list-main">
                    <span className="list-title">{item.source}</span>
                    <span className="list-sub">
                      {longDate(item.received_date)}
                      {item.notes ? ` · ${item.notes}` : ""}
                    </span>
                  </span>
                  <span className="list-end">
                    <span className="list-amount success-text">{item.amount.formatted}</span>
                  </span>
                  <ConfirmButton
                    label=""
                    icon="trash"
                    className="icon-btn"
                    confirmLabel="Sil"
                    onConfirm={async () => {
                      try {
                        await api.deleteIncome(item.id);
                        toast("Gelir silindi.");
                        state.reload();
                      } catch (cause: unknown) {
                        toast(errorMessage(cause), "danger");
                      }
                    }}
                  />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {adding && (
        <IncomeForm
          onClose={() => setAdding(false)}
          onSaved={(income) => {
            setAdding(false);
            toast("Gelir kaydedildi.");
            const saved = yearMonthOf(income.received_date);
            if (saved.year !== period.year || saved.month !== period.month) {
              setPeriod(saved);
            } else {
              state.reload();
            }
          }}
        />
      )}
    </>
  );
}

function IncomeForm({ onClose, onSaved }: { onClose: () => void; onSaved: (income: Income) => void }) {
  const { bootstrap } = useSession();
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState("Maaş");
  const [receivedDate, setReceivedDate] = useState(bootstrap.today);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const minor = parseAmountToMinor(amount);
    if (minor === null) return setError("Geçerli bir tutar girin.");
    if (!source.trim()) return setError("Gelirin kaynağını yazın.");
    setBusy(true);
    setError(null);
    try {
      const income = await api.addIncome({
        amount_minor: minor,
        received_date: receivedDate,
        source: source.trim(),
        notes: notes.trim() || null,
      });
      onSaved(income);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Gelir ekle"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form className="form-grid" onSubmit={submit} noValidate>
        <Field label="Tutar">
          <div className="input-wrap">
            <input
              className="input amount"
              inputMode="decimal"
              placeholder="0,00"
              autoFocus
              value={amount}
              onChange={(event) => setAmount(sanitiseAmount(event.target.value))}
            />
            <span className="suffix">TL</span>
          </div>
        </Field>
        <Field label="Kaynak">
          <input
            className="input"
            maxLength={64}
            value={source}
            onChange={(event) => setSource(event.target.value)}
          />
        </Field>
        <div className="chips">
          {SOURCE_SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className={suggestion === source ? "chip active" : "chip"}
              onClick={() => setSource(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
        <Field label="Tarih">
          <input
            className="input"
            type="date"
            value={receivedDate}
            onChange={(event) => setReceivedDate(event.target.value)}
          />
        </Field>
        <Field label="Not">
          <input
            className="input"
            maxLength={200}
            placeholder="İsteğe bağlı"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
