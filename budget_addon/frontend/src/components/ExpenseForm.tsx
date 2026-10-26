/**
 * Harcama formu: yeni kayıt ve düzenleme aynı formu kullanır.
 *
 * Tasarım hedefi hız: normal bir harcama birkaç dokunuşla girilebilmeli.
 * Ancak hız uğruna doğruluk feda edilmez — kredi kartı seçiliyse kaydetmeden
 * önce taksit ve ekstre özeti gösterilir (§17). Nakitte taksit her zaman 1'dir.
 *
 * "Böl" açılınca tek fiş birden çok kategoriye paylaştırılır. Parçaların
 * toplamı tutara eşit olmadan kayıt gönderilmez; asıl doğrulama sunucudadır.
 */

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { api, type Expense, type ExpenseInput, type SchedulePreview, type SplitInput } from "../api";
import { useSession } from "../context";
import {
  formatMinor,
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
const SUGGEST_DEBOUNCE_MS = 400;
const SUGGEST_MIN_LENGTH = 3;

interface Part {
  categoryId: number | null;
  amount: string;
  note: string;
}

const EMPTY_PART: Part = { categoryId: null, amount: "", note: "" };

export function ExpenseForm({
  initial,
  defaults,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Expense;
  /**
   * Hızlı girişte kategorisi bulunamayan metinden gelen tutar ve açıklama;
   * geçmiş kayıtlardan önerilen kategori varsa o da seçili gelir.
   */
  defaults?: {
    amount: string;
    description: string;
    categoryId?: number | null;
    /** Çevrimdışı girilen kaydın girildiği gün. */
    transactionDate?: string;
  };
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
    initial?.transaction_date ?? defaults?.transactionDate ?? bootstrap.today,
  );
  const [paymentMethodId, setPaymentMethodId] = useState<number | null>(() => {
    if (initial) return initial.payment_method_id;
    const cash = methods.find((method) => method.type === "cash");
    return cash?.id ?? methods[0]?.id ?? null;
  });
  const [installmentCount, setInstallmentCount] = useState(initial?.installment_count ?? 1);
  const [categoryId, setCategoryId] = useState<number | null>(
    initial?.category.id ?? defaults?.categoryId ?? null,
  );
  // Kategori geçmişten önerildiyse kullanıcıya söylenir. Kullanıcı bir kategoriye
  // kendisi dokunduysa öneri artık seçimini değiştirmez.
  const [suggested, setSuggested] = useState(Boolean(!initial && defaults?.categoryId));
  const [categoryTouched, setCategoryTouched] = useState(false);
  const suggestedRef = useRef(suggested);
  suggestedRef.current = suggested;
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

  const [splitMode, setSplitMode] = useState(Boolean(initial && initial.splits.length > 1));
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [parts, setParts] = useState<Part[]>(() =>
    initial && initial.splits.length > 1
      ? initial.splits.map((part) => ({
          categoryId: part.category_id,
          amount: minorToInput(part.amount.minor),
          note: part.note ?? "",
        }))
      : [EMPTY_PART, EMPTY_PART],
  );
  const partsMinor = parts.reduce((sum, part) => sum + (parseAmountToMinor(part.amount) ?? 0), 0);

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

  useEffect(() => {
    // Düzenlemede kayıtlı kategori korunur; öneri yalnızca yeni kayıtta yapılır.
    if (initial || categoryTouched) return;
    const text = description.trim();
    if (text.length < SUGGEST_MIN_LENGTH) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api
        .suggestCategory(text)
        .then((result) => {
          if (cancelled) return;
          const found = categories.some((category) => category.id === result.category_id);
          if (result.category_id !== null && found) {
            setCategoryId(result.category_id);
            setSuggested(true);
          } else if (suggestedRef.current) {
            // Önceki açıklamanın önerisi artık geçerli değil; kullanıcı kendisi seçer.
            setCategoryId(null);
            setSuggested(false);
          }
        })
        .catch(() => undefined);
    }, SUGGEST_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [description, initial, categoryTouched, categories]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (amountMinor === null) return setError("Geçerli bir tutar girin.");
    if (paymentMethodId === null) return setError("Ödeme yöntemi seçin.");
    let splits: SplitInput[] | undefined;
    let mainCategory = categoryId;
    if (splitMode) {
      const filled = parts.filter((part) => part.categoryId !== null || part.amount.trim());
      if (filled.length < 2) return setError("Bölmek için en az iki parça girin.");
      if (filled.some((part) => part.categoryId === null)) {
        return setError("Her parçanın kategorisini seçin.");
      }
      if (filled.some((part) => (parseAmountToMinor(part.amount) ?? 0) <= 0)) {
        return setError("Her parçanın tutarını girin.");
      }
      if (partsMinor !== amountMinor) {
        return setError(
          `Parçaların toplamı (${formatMinor(partsMinor)}) tutara (${formatMinor(amountMinor)}) eşit olmalı.`,
        );
      }
      splits = filled.map((part) => ({
        category_id: part.categoryId as number,
        amount: part.amount.trim(),
        note: part.note.trim() || null,
      }));
      mainCategory = filled[0].categoryId;
    } else if (initial && initial.splits.length > 1) {
      // Bolme kapatildi: sunucuda parcalar silinir.
      splits = [];
    }
    if (mainCategory === null) return setError("Kategori seçin.");
    if (!transactionDate) return setError("Harcama tarihini seçin.");

    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        payment_method_id: paymentMethodId,
        category_id: mainCategory,
        transaction_date: transactionDate,
        amount: amount.trim(),
        installment_count: installmentCount,
        description: description.trim() || null,
        is_shared: ownership === SHARED,
        owner_user_id: ownership === SHARED ? null : Number(ownership),
        splits,
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

      <div className="full row between">
        <span className="field-label">{splitMode ? "Parçalar" : "Kategori"}</span>
        <button
          type="button"
          className="btn ghost sm"
          aria-pressed={splitMode}
          onClick={() => {
            setSplitMode((value) => !value);
            if (!splitMode && categoryId !== null && parts[0].categoryId === null) {
              setParts([{ ...EMPTY_PART, categoryId }, EMPTY_PART]);
            }
          }}
        >
          <Icon name="split" size={16} />
          {splitMode ? "Bölmeyi kaldır" : "Birden çok kategoriye böl"}
        </button>
      </div>

      {splitMode ? (
        <div className="full split-editor">
          {parts.map((part, index) => (
            <div className="split-line" key={index}>
              <select
                className="select"
                aria-label={`${index + 1}. parçanın kategorisi`}
                value={part.categoryId ?? ""}
                onChange={(event) => {
                  const value = event.target.value ? Number(event.target.value) : null;
                  setParts((current) =>
                    current.map((item, i) => (i === index ? { ...item, categoryId: value } : item)),
                  );
                }}
              >
                <option value="">Kategori seçin</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.emoji} {category.name}
                  </option>
                ))}
              </select>
              <div className="input-wrap">
                <input
                  className="input"
                  inputMode="decimal"
                  placeholder="0,00"
                  aria-label={`${index + 1}. parçanın tutarı`}
                  value={part.amount}
                  onChange={(event) => {
                    const value = sanitiseAmount(event.target.value);
                    setParts((current) =>
                      current.map((item, i) => (i === index ? { ...item, amount: value } : item)),
                    );
                  }}
                />
                <span className="suffix">TL</span>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label={`${index + 1}. parçayı kaldır`}
                disabled={parts.length <= 2}
                onClick={() => setParts((current) => current.filter((_, i) => i !== index))}
              >
                <Icon name="close" size={16} />
              </button>
              <input
                className="input note"
                maxLength={200}
                placeholder="Not (isteğe bağlı)"
                aria-label={`${index + 1}. parçanın notu`}
                value={part.note}
                onChange={(event) => {
                  const value = event.target.value;
                  setParts((current) =>
                    current.map((item, i) => (i === index ? { ...item, note: value } : item)),
                  );
                }}
              />
            </div>
          ))}
          <div className="split-status">
            <button
              type="button"
              className="btn ghost sm"
              disabled={parts.length >= 20}
              onClick={() => setParts((current) => [...current, EMPTY_PART])}
            >
              <Icon name="plus" size={16} />
              Parça ekle
            </button>
            {amountMinor !== null && (
              <span className={partsMinor === amountMinor ? "success-text" : "muted"}>
                {partsMinor === amountMinor
                  ? "Parçalar tutara eşit"
                  : partsMinor < amountMinor
                    ? `Dağıtılacak: ${formatMinor(amountMinor - partsMinor)}`
                    : `Fazla: ${formatMinor(partsMinor - amountMinor)}`}
              </span>
            )}
            {amountMinor !== null && partsMinor < amountMinor && (
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  // Kalan tutar son bos ya da son parcaya yazilir.
                  const rest = amountMinor - partsMinor;
                  setParts((current) => {
                    const target = current.findIndex((item) => !item.amount.trim());
                    const index = target >= 0 ? target : current.length - 1;
                    return current.map((item, i) =>
                      i === index
                        ? {
                            ...item,
                            amount: minorToInput((parseAmountToMinor(item.amount) ?? 0) + rest),
                          }
                        : item,
                    );
                  });
                }}
              >
                Kalanı son parçaya yaz
              </button>
            )}
          </div>
        </div>
      ) : (
      <Field
        label="Kategori"
        className="full"
        group
        hint={
          suggested && !categoryTouched && categoryId !== null
            ? "Kural veya geçmiş kayıtlara göre önerildi; farklıysa değiştirin."
            : undefined
        }
      >
        <div className="chips">
          {(categories.length > 8 && !showAllCategories
            ? categories.filter((c, i) => i < 7 || c.id === categoryId)
            : categories
          ).map((category) => (
            <button
              key={category.id}
              type="button"
              className={category.id === categoryId ? "chip active" : "chip"}
              aria-pressed={category.id === categoryId}
              onClick={() => {
                setCategoryId(category.id);
                setCategoryTouched(true);
              }}
            >
              <span aria-hidden="true">{category.emoji}</span>
              {category.name}
            </button>
          ))}
          {categories.length > 8 && (
            <button
              type="button"
              className="chip ghost"
              onClick={() => setShowAllCategories((v) => !v)}
            >
              {showAllCategories ? "Daha az göster" : `+${categories.length - 7} kategori daha`}
            </button>
          )}
        </div>
      </Field>
      )}

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
              ? "Ortak (ev) gideri olarak kaydedilir."
              : "Seçilen kişinin yıllık kişisel bütçesinden düşer, ortak giderlere dahil olmaz."
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
