/**
 * Sabit giderler: kira, aidat, abonelik gibi her ay kendiliğinden kaydedilen
 * harcamaların şablonları.
 */

import { useState, type FormEvent } from "react";

import { api, type Category, type PaymentMethod, type RecurringExpense } from "../api";
import { Icon } from "../components/icons";
import {
  Card,
  ConfirmButton,
  Empty,
  ErrorNote,
  Field,
  Loading,
  Modal,
  PageHeader,
  Stat,
  Toggle,
  useToast,
} from "../components/ui";
import { formatMinor, minorToInput, parseAmountToMinor, sanitiseAmount } from "../format";
import { errorMessage, useAsync } from "../hooks";

export function Recurring() {
  const toast = useToast();
  const [editing, setEditing] = useState<RecurringExpense | "new" | null>(null);
  const state = useAsync(async () => {
    const [items, categories, methods] = await Promise.all([
      api.recurring(),
      api.categories(),
      api.paymentMethods(),
    ]);
    return { items, categories, methods };
  }, []);

  const header = (
    <PageHeader
      title="Sabit giderler"
      subtitle="Her ay seçilen günde harcama olarak kendiliğinden kaydedilir."
      actions={
        <button type="button" className="btn primary" onClick={() => setEditing("new")}>
          <Icon name="plus" size={18} />
          Sabit gider ekle
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

  const { items, categories, methods } = state.data;
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const methodById = new Map(methods.map((method) => [method.id, method]));
  const active = items.filter((item) => item.is_active);
  const activeTotal = active.reduce((sum, item) => sum + item.amount.minor, 0);

  return (
    <>
      {header}

      <div className="stack">
        <div className="grid stats pair">
          <Stat label="Aylık toplam" value={formatMinor(activeTotal)} icon="repeat" />
          <Stat label="Aktif şablon" value={`${active.length} / ${items.length}`} icon="list" />
        </div>

        <Card title="Şablonlar" flush>
          {items.length === 0 ? (
            <Empty
              icon="repeat"
              title="Sabit gider tanımlanmamış"
              text="Kira, aidat veya abonelik ekleyin; her ay kendiliğinden kaydedilsin."
            />
          ) : (
            <div className="list">
              {items.map((item) => {
                const category = categoryById.get(item.category_id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={item.is_active ? "list-item" : "list-item inactive"}
                    onClick={() => setEditing(item)}
                  >
                    <span className="list-icon">{category?.emoji || "🔁"}</span>
                    <span className="list-main">
                      <span className="list-title">{item.name}</span>
                      <span className="list-sub">
                        Her ayın {item.day_of_month}. günü ·{" "}
                        {methodById.get(item.payment_method_id)?.name ?? "—"}
                        {category ? ` · ${category.name}` : ""}
                      </span>
                    </span>
                    <span className="list-end">
                      <span className="list-amount">{item.amount.formatted}</span>
                      {!item.is_active && <span className="badge">Pasif</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {editing && (
        <RecurringForm
          item={editing === "new" ? null : editing}
          categories={categories}
          methods={methods}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            toast(message);
            state.reload();
          }}
        />
      )}
    </>
  );
}

function RecurringForm({
  item,
  categories,
  methods,
  onClose,
  onSaved,
}: {
  item: RecurringExpense | null;
  categories: Category[];
  methods: PaymentMethod[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(item?.name ?? "");
  const [amount, setAmount] = useState(item ? minorToInput(item.amount.minor) : "");
  const [day, setDay] = useState(String(item?.day_of_month ?? 1));
  const [categoryId, setCategoryId] = useState(
    String(item?.category_id ?? categories.find((c) => c.is_active)?.id ?? ""),
  );
  const [methodId, setMethodId] = useState(
    String(item?.payment_method_id ?? methods.find((m) => m.is_active)?.id ?? ""),
  );
  const [notes, setNotes] = useState(item?.notes ?? "");
  const [isActive, setIsActive] = useState(item?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visibleCategories = categories.filter((c) => c.is_active || c.id === item?.category_id);
  const visibleMethods = methods.filter((m) => m.is_active || m.id === item?.payment_method_id);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const minor = parseAmountToMinor(amount);
    const dayNumber = Number(day);
    if (!name.trim()) return setError("Bir ad yazın.");
    if (minor === null) return setError("Geçerli bir tutar girin.");
    if (!Number.isInteger(dayNumber) || dayNumber < 1 || dayNumber > 31) {
      return setError("Gün 1 ile 31 arasında olmalıdır.");
    }
    if (!categoryId || !methodId) return setError("Kategori ve ödeme yöntemi seçin.");

    const payload = {
      name: name.trim(),
      amount_minor: minor,
      day_of_month: dayNumber,
      category_id: Number(categoryId),
      payment_method_id: Number(methodId),
      notes: notes.trim() || null,
    };
    setBusy(true);
    setError(null);
    try {
      if (item) {
        await api.updateRecurring(item.id, { ...payload, notes: notes.trim(), is_active: isActive });
        onSaved("Sabit gider güncellendi.");
      } else {
        await api.addRecurring(payload);
        onSaved("Sabit gider eklendi.");
      }
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={item ? "Sabit gideri düzenle" : "Sabit gider ekle"}
      onClose={onClose}
      footer={
        <>
          {item && (
            <ConfirmButton
              label="Sil"
              icon="trash"
              onConfirm={async () => {
                try {
                  await api.deleteRecurring(item.id);
                  onSaved("Sabit gider silindi.");
                } catch (cause: unknown) {
                  toast(errorMessage(cause), "danger");
                }
              }}
            />
          )}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form className="form-grid two" onSubmit={submit} noValidate>
        <Field label="Ad" className="full">
          <input
            className="input"
            maxLength={64}
            placeholder="Örn. Kira"
            autoFocus={!item}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Tutar">
          <div className="input-wrap">
            <input
              className="input"
              inputMode="decimal"
              placeholder="0,00"
              value={amount}
              onChange={(event) => setAmount(sanitiseAmount(event.target.value))}
            />
            <span className="suffix">TL</span>
          </div>
        </Field>
        <Field label="Ayın günü">
          <input
            className="input"
            type="number"
            min={1}
            max={31}
            inputMode="numeric"
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
        </Field>
        <Field label="Kategori">
          <select className="select" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
            {visibleCategories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.emoji} {category.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ödeme yöntemi">
          <select className="select" value={methodId} onChange={(event) => setMethodId(event.target.value)}>
            {visibleMethods.map((method) => (
              <option key={method.id} value={method.id}>
                {method.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Not" className="full">
          <input
            className="input"
            maxLength={200}
            placeholder="İsteğe bağlı"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
        {item && (
          <div className="full">
            <Toggle
              checked={isActive}
              onChange={setIsActive}
              label="Aktif"
              hint="Pasif şablon silinmez, yalnızca her ay kaydedilmez."
            />
          </div>
        )}
        {error && (
          <div className="alert danger full" role="alert">
            {error}
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
