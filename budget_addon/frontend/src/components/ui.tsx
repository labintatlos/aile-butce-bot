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
import { createPortal } from "react-dom";

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
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    if (dialog && !dialog.contains(document.activeElement)) {
      const firstInput = dialog.querySelector<HTMLElement>(
        "input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled])",
      );
      (firstInput ?? dialog).focus();
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeRef.current();
        return;
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]):not([hidden]), [href], input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("modal-open");
      if (previousFocus && document.body.contains(previousFocus)) {
        previousFocus.focus();
      }
    };
  }, []);

  // Pencere sayfa ağacının dışına, doğrudan <body>'ye çizilir. Sayfa geçiş
  // animasyonu sarmalayıcıya transform uygular; transform taşıyan bir ata
  // `position: fixed` için kapsayıcı olur ve pencere ekrana değil uzun sayfaya
  // göre konumlanırdı (telefonda sayfanın en dibinde açılıyordu).
  return createPortal(
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={wide ? "modal wide" : "modal"}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
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
  mode = "group",
  ariaLabel,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  mode?: "tablist" | "group";
  ariaLabel?: string;
}) {
  const isTab = mode === "tablist";
  return (
    <div className="segmented" role={mode} aria-label={ariaLabel}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role={isTab ? "tab" : undefined}
            aria-selected={isTab ? active : undefined}
            aria-pressed={!isTab ? active : undefined}
            className={active ? "active" : undefined}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
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

/** Bildirimdeki düğme; "Geri al" için kullanılır. */
export interface ToastAction {
  label: string;
  run: () => Promise<void> | void;
}

type ShowToast = (message: string, tone?: ToastTone, action?: ToastAction) => void;
const ToastContext = createContext<ShowToast>(() => undefined);

const TOAST_MS = 3200;
/** Geri alınabilir işlemde kişiye düğmeye basacak zaman tanınır. */
const ACTION_TOAST_MS = 8000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{
    id: number;
    message: string;
    tone: ToastTone;
    action?: ToastAction;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const show = useCallback<ShowToast>((message, tone = "success", action) => {
    setToast({ id: Date.now(), message, tone, action });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), toast.action ? ACTION_TOAST_MS : TOAST_MS);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div key={toast.id} className={`toast ${toast.tone}`} role="status">
          <Icon name={toast.tone === "success" ? "check" : "alert"} size={18} />
          <span>{toast.message}</span>
          {toast.action && (
            <button
              type="button"
              className="toast-action"
              disabled={busy}
              onClick={async () => {
                const action = toast.action;
                if (!action) return;
                setBusy(true);
                try {
                  await action.run();
                  setToast(null);
                } catch {
                  setToast({ id: Date.now(), message: "Geri alınamadı.", tone: "danger" });
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Icon name="undo" size={16} />
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
