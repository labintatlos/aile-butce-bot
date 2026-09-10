/**
 * Yeni harcama: hızlı giriş, form ve kayıt sonrası özet.
 *
 * Hızlı giriş botta alışılan akışın aynısıdır: "500 market" yazılır, kategori
 * tek başına eşleşirse harcama bugünün tarihiyle nakit olarak hemen kaydedilir.
 * Eşleşmezse tutar ve açıklama forma aktarılır, kategori oradan seçilir.
 */

import { useState, type FormEvent } from "react";

import { api, type Expense } from "../api";
import { ExpenseForm } from "../components/ExpenseForm";
import { Icon } from "../components/icons";
import { ReceiptPanel } from "../components/ReceiptPanel";
import { Card, PageHeader } from "../components/ui";
import { useSession } from "../context";
import { installmentLabel, longDate, minorToInput } from "../format";
import { errorMessage } from "../hooks";
import { haptic } from "../telegram";

type Draft = { amount: string; description: string };

export function NewExpense() {
  const { bootstrap, navigate } = useSession();
  const [saved, setSaved] = useState<Expense | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);

  if (saved) {
    return (
      <SavedExpense
        expense={saved}
        onNew={() => {
          setSaved(null);
          setDraft(null);
          setFormKey((value) => value + 1);
        }}
        onList={() => navigate("harcamalar")}
      />
    );
  }

  return (
    <>
      <PageHeader title="Yeni harcama" subtitle={longDate(bootstrap.today)} />
      <div className="narrow stack">
        <QuickEntry
          onSaved={setSaved}
          onDraft={(next) => {
            setDraft(next);
            setFormKey((value) => value + 1);
          }}
        />
        {draft && (
          <div className="alert info" role="status">
            Kategori bulunamadı. Tutar ve açıklama forma aktarıldı; kategoriyi seçip kaydedin.
          </div>
        )}
        <Card>
          <ExpenseForm
            key={formKey}
            defaults={draft ?? undefined}
            submitLabel="Kaydet"
            onSubmit={async (input) => {
              try {
                const expense = await api.createExpense(input);
                haptic("success");
                setSaved(expense);
              } catch (cause) {
                haptic("error");
                throw cause;
              }
            }}
          />
        </Card>
      </div>
    </>
  );
}

function QuickEntry({
  onSaved,
  onDraft,
}: {
  onSaved: (expense: Expense) => void;
  onDraft: (draft: Draft) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.quickEntry(text.trim());
      if (result.expense) {
        onSaved(result.expense);
        return;
      }
      onDraft({
        amount: minorToInput(result.amount_minor ?? 0),
        description: result.description ?? "",
      });
      setText("");
    } catch (cause: unknown) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Hızlı giriş">
      <form className="stack" onSubmit={submit} noValidate>
        <div className="row">
          <input
            className="input"
            placeholder="Örn. 500 market"
            autoComplete="off"
            enterKeyHint="send"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button type="submit" className="btn primary" disabled={busy || !text.trim()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </div>
        <span className="muted small">
          Tutar ve kategori yazın; bugünün tarihiyle nakit olarak kaydedilir. #kisisel yazarsanız ortak
          gidere sayılmaz.
        </span>
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
      </form>
    </Card>
  );
}

function SavedExpense({
  expense,
  onNew,
  onList,
}: {
  expense: Expense;
  onNew: () => void;
  onList: () => void;
}) {
  const { bootstrap } = useSession();
  const [hasReceipt, setHasReceipt] = useState(expense.has_receipt);
  const method = bootstrap.payment_methods.find((item) => item.id === expense.payment_method_id);
  const isCreditCard = method?.type === "credit_card";
  const first = expense.installments[0];
  const last = expense.installments[expense.installments.length - 1];

  return (
    <div className="narrow">
      <Card>
        <div className="saved">
          <div className="success-mark">
            <Icon name="check" size={30} />
          </div>
          <h2>Harcama kaydedildi</h2>
          <p className="muted">Kayıt no {expense.public_id}</p>
          <div className="detail-amount mt">{expense.total.formatted}</div>

          <dl className="kv">
            <div>
              <dt>Kategori</dt>
              <dd>
                {expense.category.emoji} {expense.category.name}
              </dd>
            </div>
            <div>
              <dt>Ödeme yöntemi</dt>
              <dd>{expense.payment_method_name}</dd>
            </div>
            <div>
              <dt>Tarih</dt>
              <dd>{longDate(expense.transaction_date)}</dd>
            </div>
            <div>
              <dt>Taksit</dt>
              <dd>
                {installmentLabel(expense.installment_count)}
                {expense.installment_count > 1 && first ? ` · ${first.amount.formatted}` : ""}
              </dd>
            </div>
            {isCreditCard && first && (
              <div>
                <dt>İlk son ödeme</dt>
                <dd>{longDate(first.due_date)}</dd>
              </div>
            )}
            {isCreditCard && last && expense.installment_count > 1 && (
              <div>
                <dt>Son taksit</dt>
                <dd>{longDate(last.due_date)}</dd>
              </div>
            )}
            {expense.description && (
              <div>
                <dt>Açıklama</dt>
                <dd>{expense.description}</dd>
              </div>
            )}
          </dl>

          <div className="mt">
            <ReceiptPanel expenseId={expense.id} hasReceipt={hasReceipt} onChange={setHasReceipt} />
          </div>

          <div className="form-actions center">
            <button type="button" className="btn secondary" onClick={onList}>
              Harcamalara git
            </button>
            <button type="button" className="btn primary" onClick={onNew}>
              <Icon name="plus" size={18} />
              Yeni harcama
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
