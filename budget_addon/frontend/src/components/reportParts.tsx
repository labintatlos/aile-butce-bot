/**
 * Özet ve rapor ekranlarının ortak parçaları.
 *
 * Hiçbir tutar burada hesaplanmaz; sunucu her sayıyı hem kuruş hem biçimlenmiş
 * metin olarak gönderir. Kuruş değeri yalnızca çubuk genişliği için kullanılır.
 */

import type { ReactNode } from "react";

import type { BudgetStatus, CardUsage, Expense, Settlement, Statement } from "../api";
import { installmentLabel, shortDate } from "../format";
import { Icon } from "./icons";
import { Empty, Meter } from "./ui";

export function share(part: number, total: number): number {
  return total > 0 ? (part * 100) / total : 0;
}

export function BarRow({
  label,
  value,
  ratio,
  meta,
  tone,
}: {
  label: ReactNode;
  value: ReactNode;
  ratio?: number;
  meta?: ReactNode;
  tone?: "danger" | "warning";
}) {
  return (
    <div className="bar-row">
      <div className="bar-label">
        <span>{label}</span>
        <span className={tone === "danger" ? "danger-text" : undefined}>{value}</span>
      </div>
      {ratio !== undefined && <Meter ratio={ratio} tone={tone} />}
      {meta && <span className="bar-meta">{meta}</span>}
    </div>
  );
}

export function BudgetBars({ items }: { items: BudgetStatus[] }) {
  return (
    <>
      {items.map((item) => (
        <BarRow
          key={item.category_id}
          label={`${item.emoji} ${item.name}`}
          value={`${item.spent.formatted} / ${item.budget.formatted}`}
          ratio={item.ratio}
          tone={item.is_exceeded ? "danger" : item.ratio >= 80 ? "warning" : undefined}
          meta={`%${item.ratio} · ${
            item.is_exceeded ? "hedef aşıldı" : `kalan ${item.remaining.formatted}`
          }`}
        />
      ))}
    </>
  );
}

export function CardLimits({ items }: { items: CardUsage[] }) {
  return (
    <>
      {items.map((item) =>
        item.credit_limit ? (
          <BarRow
            key={item.payment_method_id}
            label={item.name}
            value={item.outstanding.formatted}
            ratio={item.ratio}
            tone={item.is_over_limit ? "danger" : item.ratio >= 90 ? "warning" : undefined}
            meta={`Limit ${item.credit_limit.formatted} · ${
              item.is_over_limit ? "limit aşıldı" : `kullanılabilir ${item.available.formatted}`
            }`}
          />
        ) : (
          <BarRow
            key={item.payment_method_id}
            label={item.name}
            value={item.outstanding.formatted}
            meta="Limit girilmemiş"
          />
        ),
      )}
    </>
  );
}

export function SettlementView({ settlement }: { settlement: Settlement }) {
  if (settlement.shared_total.minor === 0) {
    return <p className="muted">Bu ay ortak gider kaydı yok.</p>;
  }
  return (
    <>
      <dl className="kv">
        <div>
          <dt>Ortak gider</dt>
          <dd>{settlement.shared_total.formatted}</dd>
        </div>
        {settlement.balances.map((person) => (
          <div key={person.user_id}>
            <dt>{person.name}</dt>
            <dd>
              {person.paid.formatted}{" "}
              <span className="muted small">/ payı {person.share.formatted}</span>
            </dd>
          </div>
        ))}
      </dl>
      <div className="alert info mt">
        {settlement.is_even ? (
          "Hesap denk; kimsenin borcu yok."
        ) : (
          <span>
            <strong>{settlement.debtor_name}</strong>, {settlement.creditor_name} kişisine{" "}
            <strong>{settlement.transfer.formatted}</strong> ödemeli.
          </span>
        )}
      </div>
    </>
  );
}

export function StatementList({ items, limit }: { items: Statement[]; limit?: number }) {
  const rows = limit ? items.slice(0, limit) : items;
  if (rows.length === 0) {
    return <Empty icon="card" title="Yaklaşan ekstre yok" />;
  }
  return (
    <div className="list wrap-sub">
      {rows.map((row) => (
        <div className="list-item" key={`${row.payment_method_id}-${row.statement_date}`}>
          <span className="list-icon">
            <Icon name="card" size={18} />
          </span>
          <span className="list-main">
            <span className="list-title">{row.payment_method_name}</span>
            <span className="list-sub">
              Hesap kesimi {shortDate(row.statement_date)} · Son ödeme {shortDate(row.due_date)}
            </span>
          </span>
          <span className="list-end">
            <span className="list-amount">{row.total.formatted}</span>
            <span className="list-sub">{row.installment_count} taksit</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export function ExpenseRow({ expense, onOpen }: { expense: Expense; onOpen: () => void }) {
  const details = [shortDate(expense.transaction_date), expense.payment_method_name];
  if (expense.installment_count > 1) details.push(installmentLabel(expense.installment_count));
  return (
    <button type="button" className="list-item" onClick={onOpen}>
      <span className="list-icon">{expense.category.emoji || "🧾"}</span>
      <span className="list-main">
        <span className="list-title">{expense.description || expense.category.name}</span>
        <span className="list-sub">{details.join(" · ")}</span>
      </span>
      <span className="list-end">
        <span className="list-amount">{expense.total.formatted}</span>
        <span className="list-sub">{expense.created_by}</span>
      </span>
    </button>
  );
}
