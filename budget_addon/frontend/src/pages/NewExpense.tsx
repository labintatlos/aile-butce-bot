/**
 * Yeni harcama ve kayıt sonrası özet.
 */

import { useState } from "react";

import { api, type Expense } from "../api";
import { ExpenseForm } from "../components/ExpenseForm";
import { Icon } from "../components/icons";
import { Card, PageHeader } from "../components/ui";
import { useSession } from "../context";
import { installmentLabel, longDate } from "../format";
import { haptic } from "../telegram";

export function NewExpense() {
  const { bootstrap, navigate } = useSession();
  const [saved, setSaved] = useState<Expense | null>(null);
  const [formKey, setFormKey] = useState(0);

  if (saved) {
    return (
      <SavedExpense
        expense={saved}
        onNew={() => {
          setSaved(null);
          setFormKey((value) => value + 1);
        }}
        onList={() => navigate("harcamalar")}
      />
    );
  }

  return (
    <>
      <PageHeader title="Yeni harcama" subtitle={longDate(bootstrap.today)} />
      <div className="narrow">
        <Card>
          <ExpenseForm
            key={formKey}
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
