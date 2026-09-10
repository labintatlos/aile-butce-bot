/**
 * Arayüz yapı taşları: kart, istatistik, pencere, form alanı ve bildirim.
 *
 * Her sayfa aynı parçaları kullanır; böylece masaüstünde ve telefonda tüm
 * ekranlar aynı dili konuşur.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { monthName } from "../format";
import { Icon, type IconName } from "./icons";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-title">
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  action,
  children,
  className,
  flush,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={className ? `card ${className}` : "card"}>
      {(title || action) && (
        <div className="card-head">
          <h2>{title}</h2>
          {action}
        </div>
      )}
      <div className={flush ? "card-body flush" : "card-body"}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "danger" | "success";
  icon?: IconName;
}) {
  return (
    <div className={tone ? `stat ${tone}` : "stat"}>
      <div className="stat-top">
        {icon && (
          <span className="stat-icon">
            <Icon name={icon} size={16} />
          </span>
        )}
        <span>{label}</span>
      </div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/** Oran çubuğu. Taşan oran kutunun dışına akmasın diye sınırlanır. */
export function Meter({ ratio, tone }: { ratio: number; tone?: "danger" | "warning" }) {
  const width = `${Math.min(Math.max(ratio, 0), 100)}%`;
  return (
    <div className="meter">
      <div className={tone ? `meter-fill ${tone}` : "meter-fill"} style={{ width }} />
    </div>
  );
}

export function Loading({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      {label}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert danger" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn ghost sm" onClick={onRetry}>
          Tekrar dene
        </button>
      )}
    </div>
  );
}

export function Empty({
  icon = "list",
  title,
  text,
  action,
}: {
  icon?: IconName;
  title: string;
  text?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <strong>{title}</strong>
      {text && <span>{text}</span>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("modal-open");
    };
  }, []);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className={wide ? "modal wide" : "modal"} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
  className,
  group,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Birden fazla düğme içeren alanlar `label` yerine `div` ile sarılır. */
  group?: boolean;
}) {
  const classes = className ? `field ${className}` : "field";
  const content = (
    <>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </>
  );
  return group ? (
    <div className={classes} role="group" aria-label={label}>
      {content}
    </div>
  ) : (
    <label className={classes}>{content}</label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label className="toggle">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true">
        <span className="toggle-thumb" />
      </span>
      <span className="toggle-text">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </span>
    </label>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          className={option.value === value ? "active" : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export interface YearMonth {
  year: number;
  month: number;
}

export function shiftMonth({ year, month }: YearMonth, delta: number): YearMonth {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

export function MonthNav({
  value,
  onChange,
  max,
}: {
  value: YearMonth;
  onChange: (value: YearMonth) => void;
  max?: YearMonth;
}) {
  const atMax = max !== undefined && value.year * 12 + value.month >= max.year * 12 + max.month;
  return (
    <div className="month-nav">
      <button
        type="button"
        className="icon-btn"
        onClick={() => onChange(shiftMonth(value, -1))}
        aria-label="Önceki ay"
      >
        <Icon name="chevronLeft" />
      </button>
      <span>{monthName(value.year, value.month)}</span>
      <button
        type="button"
        className="icon-btn"
        disabled={atMax}
        onClick={() => onChange(shiftMonth(value, 1))}
        aria-label="Sonraki ay"
      >
        <Icon name="chevronRight" />
      </button>
    </div>
  );
}

/** Silme gibi geri alınamayan işlemler için iki adımlı düğme. */
export function ConfirmButton({
  label,
  confirmLabel = "Evet, sil",
  onConfirm,
  className = "btn danger-ghost",
  icon,
}: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  className?: string;
  icon?: IconName;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!asking) {
    return (
      <button type="button" className={className} onClick={() => setAsking(true)}>
        {icon && <Icon name={icon} size={16} />}
        {label}
      </button>
    );
  }
  return (
    <span className="confirm">
      <button
        type="button"
        className="btn danger sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onConfirm();
          } finally {
            setBusy(false);
            setAsking(false);
          }
        }}
      >
        {busy ? "Siliniyor…" : confirmLabel}
      </button>
      <button type="button" className="btn ghost sm" onClick={() => setAsking(false)}>
        Vazgeç
      </button>
    </span>
  );
}

type ToastTone = "success" | "danger";
const ToastContext = createContext<(message: string, tone?: ToastTone) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ id: number; message: string; tone: ToastTone } | null>(
    null,
  );
  const show = useCallback((message: string, tone: ToastTone = "success") => {
    setToast({ id: Date.now(), message, tone });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div key={toast.id} className={`toast ${toast.tone}`} role="status">
          <Icon name={toast.tone === "success" ? "check" : "alert"} size={18} />
          {toast.message}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
