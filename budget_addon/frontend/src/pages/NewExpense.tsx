/**
 * Yeni harcama: hızlı giriş, form ve kayıt sonrası özet.
 *
 * Hızlı giriş botta alışılan akışın aynısıdır: "500 market" yazılır, kategori
 * tek başına eşleşirse harcama bugünün tarihiyle nakit olarak hemen kaydedilir.
 * Eşleşmezse tutar ve açıklama forma aktarılır, kategori oradan seçilir.
 */

import { useState } from "react";

import { api, type Expense } from "../api";
import { ExpenseForm } from "../components/ExpenseForm";
import { Icon } from "../components/icons";
import { QueueList, QuickEntry, type Draft } from "../components/QuickEntry";
import { ReceiptPanel } from "../components/ReceiptPanel";
import { Card, PageHeader } from "../components/ui";
import { useSession } from "../context";
import { installmentLabel, longDate } from "../format";
import { discard, useOfflineQueue } from "../offline";

export function NewExpense() {
  const { bootstrap, navigate } = useSession();
  const [saved, setSaved] = useState<Expense | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const queue = useOfflineQueue();
  const openDraft = (next: Draft) => {
    setDraft(next);
    setFormKey((value) => value + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

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
        <QuickEntry onSaved={setSaved} onDraft={openDraft} />
        {draft?.queueRef && (
          <div className="alert info" role="status">
            Çevrimdışı girilen kayıt forma aktarıldı ({longDate(draft.transactionDate ?? "")}).
            Kategoriyi seçip kaydedin.
          </div>
        )}
        {draft && !draft.queueRef && (
          <div className="alert info" role="status">
            {draft.categoryId !== null
              ? `Kategori yazılmadı. Bu açıklamayla en son kullanılan kategori (${
                  bootstrap.categories.find((category) => category.id === draft.categoryId)
                    ?.name ?? ""
                }) seçildi; kontrol edip kaydedin.`
              : "Kategori bulunamadı. Tutar ve açıklama forma aktarıldı; kategoriyi seçip kaydedin."}
          </div>
        )}
        <Card>
          <ExpenseForm
            key={formKey}
            defaults={draft ?? undefined}
            submitLabel="Kaydet"
            onSubmit={async (input) => {
              const expense = await api.createExpense(input);
              if (draft?.queueRef) discard(draft.queueRef);
              setSaved(expense);
            }}
          />
        </Card>
        <QueueList items={queue.items} onComplete={openDraft} onRetry={() => void queue.flush()} />
      </div>
    </>
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
          <p className="muted">Kayıt numarası: {expense.public_id}</p>
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
                <dt>İlk ödeme tarihi</dt>
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
