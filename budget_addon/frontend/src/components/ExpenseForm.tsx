/**
 * Harcama formu: yeni kayıt ve düzenleme aynı formu kullanır.
 *
 * Tasarım hedefi hız: normal bir harcama birkaç dokunuşla girilebilmeli.
 * Ancak hız uğruna doğruluk feda edilmez — kredi kartı seçiliyse kaydetmeden
 * önce taksit ve ekstre özeti gösterilir (§17). Nakitte taksit her zaman 1'dir.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api, type Expense, type ExpenseInput, type SchedulePreview } from "../api";
import { useSession } from "../context";
import {
  installmentLabel,
  longDate,
  minorToInput,
  parseAmountToMinor,
  sanitiseAmount,
} from "../format";
import { errorMessage } from "../hooks";
import { Icon } from "./icons";
import { Field, Segmented } from "./ui";

const SHARED = "shared";

const PREVIEW_DEBOUNCE_MS = 350;

export function ExpenseForm({
  initial,
  defaults,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Expense;
  /** Hızlı girişte kategorisi bulunamayan metinden gelen tutar ve açıklama. */
  defaults?: { amount: string; description: string };
  submitLabel: string;
  onSubmit: (input: ExpenseInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const { bootstrap } = useSession();
  const methods = bootstrap.payment_methods;

  // Duzenlenen harcamanin kategorisi sonradan pasife alinmis olabilir; listede
  // yine gorunmeli ki form onu sessizce baska bir kategoriye cevirmesin.
  const categories = useMemo(() => {
    const active = bootstrap.categories;
    if (initial && !active.some((category) => category.id === initial.category.id)) {
      return [...active, initial.category];
    }
    return active;
  }, [bootstrap.categories, initial]);

  const [amount, setAmount] = useState(
    initial ? minorToInput(initial.total.minor) : (defaults?.amount ?? ""),
  );
  const [transactionDate, setTransactionDate] = useState(
    initial?.transaction_date ?? bootstrap.today,
  );
  const [paymentMethodId, setPaymentMethodId] = useState<number | null>(() => {
    if (initial) return initial.payment_method_id;
    const cash = methods.find((method) => method.type === "cash");
    return cash?.id ?? methods[0]?.id ?? null;
  });
  const [installmentCount, setInstallmentCount] = useState(initial?.installment_count ?? 1);
  const [categoryId, setCategoryId] = useState<number | null>(initial?.category.id ?? null);
  const [description, setDescription] = useState(
    initial?.description ?? defaults?.description ?? "",
  );
  // "shared" ya da kisisel harcamanin sahibinin kimligi.
  const [ownership, setOwnership] = useState<string>(
    initial?.owner_user_id ? String(initial.owner_user_id) : SHARED,
  );
  const ownershipOptions = useMemo(
    () => [
      { value: SHARED, label: "Ortak" },
      ...bootstrap.people.map((person) => ({
        value: String(person.id),
        label: `${person.display_name} kişisel`,
      })),
    ],
    [bootstrap.people],
  );

  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedMethod = methods.find((method) => method.id === paymentMethodId);
  const isCreditCard = selectedMethod?.type === "credit_card";
  const amountMinor = parseAmountToMinor(amount);

  useEffect(() => {
    if (selectedMethod && !isCreditCard) setInstallmentCount(1);
  }, [selectedMethod, isCreditCard]);

  useEffect(() => {
    if (!isCreditCard || amountMinor === null || paymentMethodId === null || !transactionDate) {
      setPreview(null);
      return;
    }
    // Her tusa basista sunucuya gitmemek icin kisa bir bekleme.
    const timer = window.setTimeout(() => {
      api
        .preview({
          payment_method_id: paymentMethodId,
          transaction_date: transactionDate,
          amount,
          installment_count: installmentCount,
        })
        .then(setPreview)
        .catch(() => setPreview(null));
    }, PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [isCreditCard, amountMinor, amount, paymentMethodId, transactionDate, installmentCount]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (amountMinor === null) return setError("Geçerli bir tutar girin.");
    if (paymentMethodId === null) return setError("Ödeme yöntemi seçin.");
    if (categoryId === null) return setError("Kategori seçin.");
    if (!transactionDate) return setError("Harcama tarihini seçin.");

    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        payment_method_id: paymentMethodId,
        category_id: categoryId,
        transaction_date: transactionDate,
        amount: amount.trim(),
        installment_count: installmentCount,
        description: description.trim() || null,
        is_shared: ownership === SHARED,
        owner_user_id: ownership === SHARED ? null : Number(ownership),
      });
    } catch (cause: unknown) {
      setError(
        errorMessage(cause, "İşlem kaydedilemedi. Verileriniz kaydedilmedi. Lütfen tekrar deneyin."),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="form-grid two" onSubmit={submit} noValidate>
      <Field label="Tutar" className="full">
        <div className="input-wrap">
          <input
            className="input amount"
            inputMode="decimal"
            placeholder="0,00"
            autoFocus={!initial}
            value={amount}
            onChange={(event) => setAmount(sanitiseAmount(event.target.value))}
          />
          <span className="suffix">TL</span>
        </div>
      </Field>

      <Field label="Harcama tarihi">
        <input
          className="input"
          type="date"
          value={transactionDate}
          max={bootstrap.today}
          onChange={(event) => setTransactionDate(event.target.value)}
        />
      </Field>

      <Field
        label="Taksit"
        hint={isCreditCard ? undefined : "Taksit yalnızca kredi kartında seçilebilir."}
      >
        <select
          className="select"
          value={installmentCount}
          disabled={!isCreditCard}
          onChange={(event) => setInstallmentCount(Number(event.target.value))}
        >
          {Array.from({ length: bootstrap.max_installments }, (_, index) => index + 1).map(
            (count) => (
              <option key={count} value={count}>
                {installmentLabel(count)}
              </option>
            ),
          )}
        </select>
      </Field>

      <Field label="Ödeme yöntemi" className="full" group>
        <div className="chips">
          {methods.map((method) => (
            <button
              key={method.id}
              type="button"
              className={method.id === paymentMethodId ? "chip active" : "chip"}
              aria-pressed={method.id === paymentMethodId}
              onClick={() => setPaymentMethodId(method.id)}
            >
              <Icon name={method.type === "credit_card" ? "card" : "wallet"} size={16} />
              {method.name}
            </button>
          ))}
          {initial && !selectedMethod && (
            <span className="chip active" aria-disabled="true">
              {initial.payment_method_name}
            </span>
          )}
        </div>
      </Field>

      <Field label="Kategori" className="full" group>
        <div className="chips">
          {categories.map((category) => (
            <button
              key={category.id}
              type="button"
              className={category.id === categoryId ? "chip active" : "chip"}
              aria-pressed={category.id === categoryId}
              onClick={() => setCategoryId(category.id)}
            >
              <span aria-hidden="true">{category.emoji}</span>
              {category.name}
            </button>
          ))}
        </div>
      </Field>

      <Field
        label="Açıklama"
        className="full"
        hint="İsteğe bağlı. #tatil gibi bir etiket yazarak harcamaları gruplayabilirsiniz."
      >
        <input
          className="input"
          maxLength={200}
          placeholder="Örn. haftalık market #ev"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>

      <div className="full">
        <Field
          label="Kimin harcaması?"
          hint={
            ownership === SHARED
              ? "Ortak gider olarak denkleştirmeye girer."
              : "Seçilen kişinin yıllık kişisel bütçesinden düşer, denkleştirmeye girmez."
          }
        >
          <Segmented options={ownershipOptions} value={ownership} onChange={setOwnership} />
        </Field>
      </div>

      {preview && isCreditCard && (
        <div className="preview full">
          <dl className="kv">
            <div>
              <dt>Taksit</dt>
              <dd>
                {preview.installment_count > 1
                  ? `${preview.installment_count} × ${preview.installment_amount.formatted}`
                  : `Peşin · ${preview.total.formatted}`}
              </dd>
            </div>
            {preview.first_statement_date && (
              <div>
                <dt>İlk ekstre</dt>
                <dd>{longDate(preview.first_statement_date)}</dd>
              </div>
            )}
            {preview.first_due_date && (
              <div>
                <dt>İlk ödeme tarihi</dt>
                <dd>{longDate(preview.first_due_date)}</dd>
              </div>
            )}
            {preview.last_due_date && preview.installment_count > 1 && (
              <div>
                <dt>Son taksit</dt>
                <dd>{longDate(preview.last_due_date)}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {error && (
        <div className="alert danger full" role="alert">
          {error}
        </div>
      )}

      <div className="form-actions full">
        {onCancel && (
          <button type="button" className="btn ghost" onClick={onCancel}>
            Vazgeç
          </button>
        )}
        <button type="submit" className="btn primary lg" disabled={saving}>
          {saving ? "Kaydediliyor…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
