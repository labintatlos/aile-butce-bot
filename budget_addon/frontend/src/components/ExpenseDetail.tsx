/**
 * Harcama ayrıntısı: taksitler, iadeler, düzenleme ve silme.
 *
 * Silme sunucuda yumuşak silmedir; kayıt denetim izinde kalır.
 */

import { useState, type FormEvent } from "react";

import { api, type Expense, type ExpenseInput } from "../api";
import { useSession } from "../context";
import {
  formatMinor,
  installmentLabel,
  longDate,
  parseAmountToMinor,
  sanitiseAmount,
  shortDate,
} from "../format";
import { errorMessage, useAsync } from "../hooks";
import { ExpenseForm } from "./ExpenseForm";
import { Icon } from "./icons";
import { ReceiptPanel } from "./ReceiptPanel";
import { ConfirmButton, ErrorNote, Field, Loading, Modal, useToast } from "./ui";

const STATUS_LABELS: Record<string, string> = {
  pending: "Bekliyor",
  scheduled: "Bekliyor",
  billed: "Ekstrede",
  paid: "Ödendi",
  cancelled: "İptal",
  canceled: "İptal",
};

function changedFields(item: Expense, input: ExpenseInput): Partial<ExpenseInput> {
  const changes: Partial<ExpenseInput> = {};
  if (parseAmountToMinor(input.amount) !== item.total.minor) changes.amount = input.amount;
  if (input.transaction_date !== item.transaction_date) {
    changes.transaction_date = input.transaction_date;
  }
  if (input.payment_method_id !== item.payment_method_id) {
    changes.payment_method_id = input.payment_method_id;
  }
  if (input.installment_count !== item.installment_count) {
    changes.installment_count = input.installment_count;
  }
  if (input.category_id !== item.category.id) changes.category_id = input.category_id;
  if ((input.description ?? "") !== (item.description ?? "")) {
    changes.description = input.description ?? "";
  }
  if (input.is_shared !== item.is_shared) changes.is_shared = input.is_shared;
  return changes;
}

export function ExpenseDetail({
  expenseId,
  onClose,
  onChanged,
}: {
  expenseId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [addingRefund, setAddingRefund] = useState(false);
  const expense = useAsync(() => api.getExpense(expenseId), [expenseId]);
  const refunds = useAsync(() => api.refunds(expenseId), [expenseId]);

  const title = editing ? "Harcamayı düzenle" : "Harcama ayrıntısı";

  if (!expense.data) {
    return (
      <Modal title={title} onClose={onClose}>
        {expense.error ? (
          <ErrorNote message={expense.error} onRetry={expense.reload} />
        ) : (
          <Loading />
        )}
      </Modal>
    );
  }

  const item = expense.data;

  if (editing) {
    return (
      <Modal title={title} onClose={onClose} wide>
        <ExpenseForm
          initial={item}
          submitLabel="Değişiklikleri kaydet"
          onCancel={() => setEditing(false)}
          onSubmit={async (input) => {
            const changes = changedFields(item, input);
            if (Object.keys(changes).length > 0) {
              await api.updateExpense(item.id, changes);
              toast("Harcama güncellendi.");
              expense.reload();
              onChanged();
            }
            setEditing(false);
          }}
        />
      </Modal>
    );
  }

  const refundList = refunds.data ?? [];
  const refundedMinor = refundList.reduce((sum, refund) => sum + refund.amount.minor, 0);

  return (
    <Modal
      title={title}
      onClose={onClose}
      wide
      footer={
        <>
          <ConfirmButton
            label="Sil"
            icon="trash"
            onConfirm={async () => {
              try {
                await api.deleteExpense(item.id);
                toast("Harcama silindi.");
                onChanged();
                onClose();
              } catch (cause: unknown) {
                toast(errorMessage(cause), "danger");
              }
            }}
          />
          <span className="spacer" />
          <button type="button" className="btn secondary" onClick={() => setAddingRefund(true)}>
            <Icon name="refund" size={16} />
            İade ekle
          </button>
          <button type="button" className="btn primary" onClick={() => setEditing(true)}>
            <Icon name="edit" size={16} />
            Düzenle
          </button>
        </>
      }
    >
      <div className="detail-head">
        <span className="list-icon large">{item.category.emoji || "🧾"}</span>
        <div className="list-main">
          <div className="detail-amount">{item.total.formatted}</div>
          <div className="muted">{item.description || item.category.name}</div>
        </div>
      </div>

      <div className="badges">
        <span className="badge accent">{installmentLabel(item.installment_count)}</span>
        <span className="badge">{item.is_shared ? "Ortak gider" : "Kişisel"}</span>
        {item.tags.map((tag) => (
          <span className="badge" key={tag}>
            #{tag}
          </span>
        ))}
        {item.has_receipt && <span className="badge success">Fiş eklendi</span>}
      </div>

      <div className="mt">
        <ReceiptPanel
          expenseId={item.id}
          hasReceipt={item.has_receipt}
          onChange={() => {
            expense.reload();
            onChanged();
          }}
        />
      </div>

      <dl className="kv">
        <div>
          <dt>Tarih</dt>
          <dd>{longDate(item.transaction_date)}</dd>
        </div>
        <div>
          <dt>Kategori</dt>
          <dd>
            {item.category.emoji} {item.category.name}
          </dd>
        </div>
        <div>
          <dt>Ödeme yöntemi</dt>
          <dd>{item.payment_method_name}</dd>
        </div>
        <div>
          <dt>Kaydeden</dt>
          <dd>{item.created_by}</dd>
        </div>
        <div>
          <dt>Kayıt numarası</dt>
          <dd>{item.public_id}</dd>
        </div>
        {refundedMinor > 0 && (
          <div>
            <dt>İade edilen</dt>
            <dd className="success-text">{formatMinor(refundedMinor)}</dd>
          </div>
        )}
      </dl>

      {item.installments.length > 1 && (
        <>
          <h3 className="section-title">Taksitler</h3>
          <div className="table-wrap">
            <table className="table compact">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Ekstre</th>
                  <th>Son ödeme</th>
                  <th>Durum</th>
                  <th className="right">Tutar</th>
                </tr>
              </thead>
              <tbody>
                {item.installments.map((line) => (
                  <tr key={line.number}>
                    <td>
                      {line.number}/{line.count}
                    </td>
                    <td>{shortDate(line.statement_date)}</td>
                    <td>{shortDate(line.due_date)}</td>
                    <td>
                      <span className="badge">{STATUS_LABELS[line.status] ?? line.status}</span>
                    </td>
                    <td className="right">{line.amount.formatted}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3 className="section-title">İadeler</h3>
      {refunds.error && <ErrorNote message={refunds.error} onRetry={refunds.reload} />}
      {refundList.length === 0 && !addingRefund && <p className="muted small">İade kaydı yok.</p>}
      {refundList.length > 0 && (
        <div className="list bordered">
          {refundList.map((refund) => (
            <div className="list-item" key={refund.id}>
              <span className="list-main">
                <span className="list-title success-text">{refund.amount.formatted}</span>
                <span className="list-sub">
                  {longDate(refund.refund_date)}
                  {refund.due_date ? ` · ${shortDate(refund.due_date)} ödemesinden düşer` : ""}
                  {refund.notes ? ` · ${refund.notes}` : ""}
                </span>
              </span>
              <ConfirmButton
                label=""
                icon="trash"
                className="icon-btn"
                confirmLabel="Sil"
                onConfirm={async () => {
                  try {
                    await api.deleteRefund(refund.id);
                    toast("İade silindi.");
                    refunds.reload();
                    onChanged();
                  } catch (cause: unknown) {
                    toast(errorMessage(cause), "danger");
                  }
                }}
              />
            </div>
          ))}
        </div>
      )}
      {addingRefund && (
        <RefundForm
          expenseId={item.id}
          onCancel={() => setAddingRefund(false)}
          onSaved={() => {
            setAddingRefund(false);
            toast("İade kaydedildi.");
            refunds.reload();
            onChanged();
          }}
        />
      )}
    </Modal>
  );
}

function RefundForm({
  expenseId,
  onSaved,
  onCancel,
}: {
  expenseId: number;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { bootstrap } = useSession();
  const [amount, setAmount] = useState("");
  const [refundDate, setRefundDate] = useState(bootstrap.today);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const minor = parseAmountToMinor(amount);
    if (minor === null) return setError("Geçerli bir iade tutarı girin.");
    setBusy(true);
    setError(null);
    try {
      await api.addRefund(expenseId, {
        amount_minor: minor,
        refund_date: refundDate,
        notes: notes.trim() || null,
      });
      onSaved();
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <form className="inline-form form-grid two" onSubmit={submit} noValidate>
      <Field label="İade tutarı">
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
      <Field label="İade tarihi">
        <input
          className="input"
          type="date"
          value={refundDate}
          max={bootstrap.today}
          onChange={(event) => setRefundDate(event.target.value)}
        />
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
      {error && (
        <div className="alert danger full" role="alert">
          {error}
        </div>
      )}
      <div className="form-actions full">
        <button type="button" className="btn ghost" onClick={onCancel}>
          Vazgeç
        </button>
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Kaydediliyor…" : "İadeyi kaydet"}
        </button>
      </div>
    </form>
  );
}
