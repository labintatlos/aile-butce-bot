/**
 * Kişisel yıllık bütçeler: kişi başı harcanan, kalan ve yılın ne kadarının
 * geçtiği. Tutarlar sunucudan gelir; burada hesaplanmaz.
 */

import { useState, type FormEvent } from "react";

import { api, type PersonalBudget } from "../api";
import { minorToInput } from "../format";
import { errorMessage, useAsync } from "../hooks";
import { Card, ErrorNote, Field, Loading, Meter, Modal, useToast } from "./ui";

export function PersonalBudgetsCard({ year }: { year: number }) {
  const state = useAsync(() => api.personalBudgets(year), [year]);
  const [editing, setEditing] = useState(false);

  return (
    <Card
      title={`Kişisel bütçeler · ${year}`}
      action={
        state.data && (
          <button type="button" className="btn ghost sm" onClick={() => setEditing(true)}>
            Düzenle
          </button>
        )
      }
    >
      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}
      {state.data && (
        <div className="stack">
          {state.data.map((item) => (
            <PersonRow key={item.user_id} item={item} />
          ))}
        </div>
      )}
      {editing && state.data && (
        <BudgetForm
          year={year}
          items={state.data}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            state.reload();
          }}
        />
      )}
    </Card>
  );
}

function PersonRow({ item }: { item: PersonalBudget }) {
  if (!item.budget) {
    return (
      <div>
        <div className="row between">
          <strong>{item.name}</strong>
          <span>{item.spent.formatted}</span>
        </div>
        <p className="muted">Bütçe belirlenmedi · {item.expense_count} harcama</p>
      </div>
    );
  }
  const ahead = !item.is_exceeded && item.ratio > item.year_elapsed_ratio + 10;
  return (
    <div>
      <div className="row between">
        <strong>{item.name}</strong>
        <span>
          {item.spent.formatted} / {item.budget.formatted}
        </span>
      </div>
      <Meter
        ratio={Math.min(item.ratio, 100)}
        tone={item.is_exceeded ? "danger" : ahead ? "warning" : undefined}
      />
      <p className="muted">
        {item.is_exceeded
          ? `Bütçe ${item.remaining!.formatted.replace("-", "")} aşıldı`
          : `Kalan ${item.remaining!.formatted}`}
        {` · %${item.ratio} harcandı, yılın %${item.year_elapsed_ratio}'i geçti`}
      </p>
    </div>
  );
}

function BudgetForm({
  year,
  items,
  onClose,
  onSaved,
}: {
  year: number;
  items: PersonalBudget[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [amounts, setAmounts] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      items.map((item) => [item.user_id, item.budget ? minorToInput(item.budget.minor) : ""]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      for (const item of items) {
        const next = (amounts[item.user_id] ?? "").trim();
        const current = item.budget ? minorToInput(item.budget.minor) : "";
        if (next !== current) await api.setPersonalBudget(item.user_id, year, next || null);
      }
      toast("Kişisel bütçeler kaydedildi.");
      onSaved();
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${year} kişisel bütçeleri`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" form="personal-budget-form" className="btn primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form id="personal-budget-form" className="stack" onSubmit={submit} noValidate>
        {items.map((item) => (
          <Field
            key={item.user_id}
            label={`${item.name} yıllık bütçesi`}
            hint="Boş bırakırsanız bu yıl için bütçe kaldırılır."
          >
            <input
              className="input"
              inputMode="decimal"
              placeholder="Örn. 40.000"
              value={amounts[item.user_id] ?? ""}
              onChange={(event) =>
                setAmounts((prev) => ({ ...prev, [item.user_id]: event.target.value }))
              }
            />
          </Field>
        ))}
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
