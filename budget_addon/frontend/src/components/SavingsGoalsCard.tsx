/**
 * Birikim hedefleri: biriken, hedefe kalan ve her ay ayrılması gereken tutar.
 *
 * Hesap sunucuda yapılır (bkz. `services/savings.py`); burada yalnızca
 * gösterilir. Kart, bu ayın kalanının hedeflere yetip yetmediğini de söyler.
 */

import { useState, type FormEvent } from "react";

import { api, type SavingsGoal, type SavingsOverview } from "../api";
import { useSession } from "../context";
import { longDate, minorToInput, monthName, parseAmountToMinor, sanitiseAmount } from "../format";
import { errorMessage, useAsync } from "../hooks";
import { Icon } from "./icons";
import {
  Card,
  ConfirmButton,
  Empty,
  ErrorNote,
  Field,
  Loading,
  Meter,
  Modal,
  Segmented,
  useToast,
} from "./ui";

type Editing =
  | { kind: "new" }
  | { kind: "edit"; goal: SavingsGoal }
  | { kind: "deposit"; goal: SavingsGoal };

export function SavingsGoalsCard() {
  const state = useAsync(() => api.savingsGoals(), []);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [data, setData] = useState<SavingsOverview | null>(null);
  const overview = data ?? state.data;

  const done = (next?: SavingsOverview) => {
    setEditing(null);
    if (next) setData(next);
    else {
      setData(null);
      state.reload();
    }
  };

  return (
    <Card
      title="Birikim hedefleri"
      action={
        overview && (
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setEditing({ kind: "new" })}
          >
            <Icon name="plus" size={16} />
            Yeni hedef
          </button>
        )
      }
    >
      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!overview && !state.error && <Loading />}
      {overview && overview.goals.length === 0 && (
        <Empty
          icon="wallet"
          title="Henüz birikim hedefi yok"
          text="Örneğin “Tatil için Haziran'a kadar 50.000 TL”: ayda ne kadar ayırmanız gerektiğini hesaplar."
        />
      )}
      {overview && overview.goals.length > 0 && (
        <div className="stack">
          <MonthSummary overview={overview} />
          {overview.goals.map((goal) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              onDeposit={() => setEditing({ kind: "deposit", goal })}
              onEdit={() => setEditing({ kind: "edit", goal })}
            />
          ))}
        </div>
      )}

      {editing?.kind === "new" && <GoalForm onClose={() => setEditing(null)} onSaved={done} />}
      {editing?.kind === "edit" && (
        <GoalForm goal={editing.goal} onClose={() => setEditing(null)} onSaved={done} />
      )}
      {editing?.kind === "deposit" && (
        <DepositForm goal={editing.goal} onClose={() => setEditing(null)} onSaved={done} />
      )}
    </Card>
  );
}

function MonthSummary({ overview }: { overview: SavingsOverview }) {
  if (overview.monthly_required.minor === 0) return null;
  const required = overview.monthly_required.formatted;
  if (overview.covers === null || overview.month_remaining === null) {
    return (
      <p className="muted small">
        Hedefler için bu ay {required} ayırmanız gerekiyor. Bu ayın gelirini girerseniz yetip
        yetmediği de gösterilir.
      </p>
    );
  }
  return (
    <div className={overview.covers ? "alert info" : "alert danger"} role="status">
      <span>
        Hedefler için bu ay {required} gerekiyor; ayın kalanı {overview.month_remaining.formatted}.{" "}
        {overview.covers ? "Yetiyor." : "Bu gidişle yetmiyor."}
      </span>
    </div>
  );
}

function deadlineText(goal: SavingsGoal): string {
  const [year, month] = goal.target_date.split("-").map(Number);
  const deadline = monthName(year, month);
  if (goal.is_complete) return `Hedefe ulaşıldı · ${deadline}`;
  if (goal.is_overdue) {
    return `Süresi geçti (${longDate(goal.target_date)}) · kalan ${goal.remaining.formatted}`;
  }
  const months = goal.months_left === 1 ? "bu ay son" : `${goal.months_left} ay kaldı`;
  return `Ayda ${goal.monthly_required.formatted} · ${months} (${deadline})`;
}

function GoalRow({
  goal,
  onDeposit,
  onEdit,
}: {
  goal: SavingsGoal;
  onDeposit: () => void;
  onEdit: () => void;
}) {
  return (
    <div>
      <div className="row between">
        <strong>{goal.name}</strong>
        <span>
          {goal.saved.formatted} / {goal.target.formatted}
        </span>
      </div>
      <Meter ratio={goal.ratio} tone={goal.is_overdue ? "danger" : undefined} />
      <div className="row between">
        <p className="muted small">{deadlineText(goal)}</p>
        <span className="row">
          <button type="button" className="btn ghost sm" onClick={onDeposit}>
            Para ekle
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={onEdit}
            aria-label={`${goal.name} hedefini düzenle`}
          >
            <Icon name="edit" size={16} />
          </button>
        </span>
      </div>
    </div>
  );
}

function GoalForm({
  goal,
  onClose,
  onSaved,
}: {
  goal?: SavingsGoal;
  onClose: () => void;
  onSaved: (next?: SavingsOverview) => void;
}) {
  const { bootstrap } = useSession();
  const toast = useToast();
  const [name, setName] = useState(goal?.name ?? "");
  const [target, setTarget] = useState(goal ? minorToInput(goal.target.minor) : "");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const targetMinor = parseAmountToMinor(target);
    const savedMinor = saved.trim() ? parseAmountToMinor(saved) : 0;
    if (!name.trim()) return setError("Hedefe bir ad verin.");
    if (targetMinor === null || targetMinor <= 0) return setError("Geçerli bir hedef tutar girin.");
    if (!targetDate) return setError("Hedef tarihi seçin.");
    if (savedMinor === null) return setError("Biriken tutar geçerli değil.");
    setBusy(true);
    setError(null);
    try {
      const next = goal
        ? await api.updateSavingsGoal(goal.id, {
            name: name.trim(),
            target_minor: targetMinor,
            target_date: targetDate,
          })
        : await api.addSavingsGoal({
            name: name.trim(),
            target_minor: targetMinor,
            target_date: targetDate,
            saved_minor: savedMinor,
          });
      toast(goal ? "Hedef güncellendi." : "Birikim hedefi eklendi.");
      onSaved(next);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={goal ? "Hedefi düzenle" : "Yeni birikim hedefi"}
      onClose={onClose}
      footer={
        <>
          {goal && (
            <ConfirmButton
              label="Sil"
              icon="trash"
              onConfirm={async () => {
                try {
                  await api.deleteSavingsGoal(goal.id);
                  toast("Hedef silindi.");
                  onSaved();
                } catch (cause: unknown) {
                  setError(errorMessage(cause));
                }
              }}
            />
          )}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" form="savings-goal-form" className="btn primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form id="savings-goal-form" className="form-grid two" onSubmit={submit} noValidate>
        <Field label="Hedef" className="full">
          <input
            className="input"
            maxLength={80}
            placeholder="Örn. Yaz tatili"
            autoFocus={!goal}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Hedef tutar">
          <div className="input-wrap">
            <input
              className="input"
              inputMode="decimal"
              placeholder="0,00"
              value={target}
              onChange={(event) => setTarget(sanitiseAmount(event.target.value))}
            />
            <span className="suffix">TL</span>
          </div>
        </Field>
        <Field label="Ne zamana kadar?">
          <input
            className="input"
            type="date"
            min={goal ? undefined : bootstrap.today}
            value={targetDate}
            onChange={(event) => setTargetDate(event.target.value)}
          />
        </Field>
        {!goal && (
          <Field label="Şimdiden biriken" className="full" hint="İsteğe bağlı. Kenarda duran tutar.">
            <div className="input-wrap">
              <input
                className="input"
                inputMode="decimal"
                placeholder="0,00"
                value={saved}
                onChange={(event) => setSaved(sanitiseAmount(event.target.value))}
              />
              <span className="suffix">TL</span>
            </div>
          </Field>
        )}
        {error && (
          <div className="alert danger full" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}

const DIRECTIONS = [
  { value: "add", label: "Kenara koydum" },
  { value: "take", label: "Birikimden aldım" },
] as const;

function DepositForm({
  goal,
  onClose,
  onSaved,
}: {
  goal: SavingsGoal;
  onClose: () => void;
  onSaved: (next: SavingsOverview) => void;
}) {
  const toast = useToast();
  const [direction, setDirection] = useState<"add" | "take">("add");
  const [amount, setAmount] = useState(
    goal.monthly_required.minor > 0 ? minorToInput(goal.monthly_required.minor) : "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const minor = parseAmountToMinor(amount);
    if (minor === null || minor <= 0) return setError("Geçerli bir tutar girin.");
    setBusy(true);
    setError(null);
    try {
      const next = await api.depositSavings(goal.id, direction === "add" ? minor : -minor);
      toast(direction === "add" ? "Birikime eklendi." : "Birikimden düşüldü.");
      onSaved(next);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={goal.name}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" form="savings-deposit-form" className="btn primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form id="savings-deposit-form" className="stack" onSubmit={submit} noValidate>
        <Segmented options={DIRECTIONS} value={direction} onChange={setDirection} />
        <Field
          label="Tutar"
          hint={`Biriken: ${goal.saved.formatted} · Hedefe kalan: ${goal.remaining.formatted}`}
        >
          <div className="input-wrap">
            <input
              className="input"
              inputMode="decimal"
              placeholder="0,00"
              autoFocus
              value={amount}
              onChange={(event) => setAmount(sanitiseAmount(event.target.value))}
            />
            <span className="suffix">TL</span>
          </div>
        </Field>
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
