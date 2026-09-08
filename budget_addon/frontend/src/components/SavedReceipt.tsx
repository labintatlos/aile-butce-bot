import type { Expense } from "../api";
import { installmentLabel, longDate } from "../format";

interface Props {
  expense: Expense;
  onNew: () => void;
}

/** Kayıt sonrası özet. Bot da aynı bilgileri mesaj olarak gönderir (§18). */
export function SavedReceipt({ expense, onNew }: Props) {
  return (
    <main className="screen">
      <section className="saved">
        <p className="saved-title">✅ Harcama kaydedildi</p>
        <p className="saved-amount">{expense.total.formatted}</p>
        <p className="hint">
          {expense.category.emoji} {expense.category.name}
          {expense.description ? ` · ${expense.description}` : ""}
        </p>
        <div className="preview">
          <div className="preview-row">
            <span>Ödeme</span>
            <strong>{expense.payment_method_name}</strong>
          </div>
          <div className="preview-row">
            <span>Taksit</span>
            <strong>{installmentLabel(expense.installment_count)}</strong>
          </div>
          <div className="preview-row">
            <span>Tarih</span>
            <strong>{longDate(expense.transaction_date)}</strong>
          </div>
          <div className="preview-row">
            <span>İşlem</span>
            <strong>#{expense.public_id}</strong>
          </div>
        </div>
      </section>

      <button className="submit" type="button" onClick={onNew}>
        YENİ HARCAMA
      </button>
    </main>
  );
}
