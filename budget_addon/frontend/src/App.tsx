/**
 * Harcama giriş formu.
 *
 * Aynı bileşen üç bağlamda çalışır: Home Assistant paneli, Telegram Mini App
 * ve tarayıcı. Fark yalnızca kimliğin nereden geldiğidir (bkz. api.ts).
 *
 * Tasarım hedefi hız: normal bir harcama az sayıda dokunuşla girilebilmeli.
 * Ancak hız uğruna doğruluk feda edilmez — kredi kartı seçiliyse kaydetmeden
 * önce taksit ve ekstre özeti gösterilir (§17).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  api,
  type Bootstrap,
  type Expense,
  type PaymentMethod,
  type SchedulePreview,
} from "./api";
import { AmountInput } from "./components/AmountInput";
import { CategoryPicker } from "./components/CategoryPicker";
import { InstallmentPicker } from "./components/InstallmentPicker";
import { PaymentMethodPicker } from "./components/PaymentMethodPicker";
import { SchedulePreviewCard } from "./components/SchedulePreview";
import { SavedReceipt } from "./components/SavedReceipt";
import { Reports } from "./components/Reports";
import { longDate, looksLikeAmount } from "./format";
import { applyTelegramTheme, haptic } from "./telegram";

const PREVIEW_DEBOUNCE_MS = 350;

type View = "add" | "report";

export default function App() {
  const [view, setView] = useState<View>("add");
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [amount, setAmount] = useState("");
  const [transactionDate, setTransactionDate] = useState("");
  const [paymentMethodId, setPaymentMethodId] = useState<number | null>(null);
  const [installmentCount, setInstallmentCount] = useState(1);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [description, setDescription] = useState("");

  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Expense | null>(null);

  useEffect(() => {
    applyTelegramTheme();
    api
      .bootstrap()
      .then((data) => {
        setBootstrap(data);
        setTransactionDate(data.today);
        const cash = data.payment_methods.find((m) => m.type === "cash");
        setPaymentMethodId(cash?.id ?? data.payment_methods[0]?.id ?? null);
      })
      .catch((error: unknown) =>
        setLoadError(error instanceof ApiError ? error.message : "Bağlantı kurulamadı."),
      );
  }, []);

  const selectedMethod: PaymentMethod | undefined = useMemo(
    () => bootstrap?.payment_methods.find((m) => m.id === paymentMethodId),
    [bootstrap, paymentMethodId],
  );
  const isCreditCard = selectedMethod?.type === "credit_card";

  // Nakit secildiginde taksit her zaman 1'dir (§8).
  useEffect(() => {
    if (!isCreditCard) setInstallmentCount(1);
  }, [isCreditCard]);

  const canPreview =
    isCreditCard && looksLikeAmount(amount) && paymentMethodId !== null && transactionDate !== "";

  useEffect(() => {
    if (!canPreview || paymentMethodId === null) {
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
  }, [canPreview, paymentMethodId, transactionDate, amount, installmentCount]);

  const ready =
    looksLikeAmount(amount) &&
    transactionDate !== "" &&
    paymentMethodId !== null &&
    categoryId !== null &&
    !saving;

  const submit = useCallback(async () => {
    if (!ready || paymentMethodId === null || categoryId === null) return;
    setSaving(true);
    setSaveError(null);
    try {
      const expense = await api.createExpense({
        payment_method_id: paymentMethodId,
        category_id: categoryId,
        transaction_date: transactionDate,
        amount,
        installment_count: installmentCount,
        description: description.trim() || null,
      });
      haptic("success");
      setSaved(expense);
    } catch (error: unknown) {
      haptic("error");
      setSaveError(
        error instanceof ApiError
          ? error.message
          : "İşlem kaydedilemedi. Verileriniz kaydedilmedi. Lütfen tekrar deneyin.",
      );
    } finally {
      setSaving(false);
    }
  }, [ready, paymentMethodId, categoryId, transactionDate, amount, installmentCount, description]);

  const reset = useCallback(() => {
    setSaved(null);
    setAmount("");
    setDescription("");
    setInstallmentCount(1);
    setPreview(null);
  }, []);

  if (loadError) {
    return (
      <main className="screen">
        <p className="error" role="alert">
          {loadError}
        </p>
      </main>
    );
  }

  // Sekmeler her iki gorunumde de aynidir; tek yerde tanimlanip ikisine de
  // verilir ki biri degisince digeri geride kalmasin.
  const tabs = (
    <nav className="tabs">
      <button
        type="button"
        className={view === "add" ? "tab active" : "tab"}
        onClick={() => setView("add")}
      >
        Harcama Ekle
      </button>
      <button
        type="button"
        className={view === "report" ? "tab active" : "tab"}
        onClick={() => setView("report")}
      >
        Rapor
      </button>
    </nav>
  );

  if (!bootstrap) {
    return (
      <main className="screen">
        <p className="hint">Yükleniyor…</p>
      </main>
    );
  }

  if (view === "report") {
    return (
      <>
        {tabs}
        <Reports />
      </>
    );
  }

  if (saved) {
    return <SavedReceipt expense={saved} onNew={reset} />;
  }

  return (
    <>
    {tabs}
    <main className="screen">
      <header className="header">
        <h1>Harcama Ekle</h1>
        <p className="hint">
          {bootstrap.user.display_name} · {longDate(transactionDate || bootstrap.today)}
        </p>
      </header>

      <AmountInput value={amount} onChange={setAmount} />

      <label className="field">
        <span className="label">Harcama Tarihi</span>
        <input
          className="control"
          type="date"
          value={transactionDate}
          max={bootstrap.today}
          onChange={(event) => setTransactionDate(event.target.value)}
        />
      </label>

      <PaymentMethodPicker
        methods={bootstrap.payment_methods}
        selectedId={paymentMethodId}
        onSelect={setPaymentMethodId}
      />

      <InstallmentPicker
        value={installmentCount}
        max={bootstrap.max_installments}
        disabled={!isCreditCard}
        onChange={setInstallmentCount}
      />

      <CategoryPicker
        categories={bootstrap.categories}
        selectedId={categoryId}
        onSelect={setCategoryId}
      />

      <label className="field">
        <span className="label">Açıklama</span>
        <input
          className="control"
          type="text"
          inputMode="text"
          placeholder="İsteğe bağlı"
          maxLength={200}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>

      {preview && <SchedulePreviewCard preview={preview} />}

      {saveError && (
        <p className="error" role="alert">
          {saveError}
        </p>
      )}

      <button className="submit" type="button" disabled={!ready} onClick={submit}>
        {saving ? "KAYDEDİLİYOR…" : "KAYDET"}
      </button>
    </main>
    </>
  );
}
