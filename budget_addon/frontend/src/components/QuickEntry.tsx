/**
 * Hızlı giriş ("500 market") ve çevrimdışı bekleyen kayıtlar.
 *
 * Bağlantı varsa metin hemen sunucuya gider. Yoksa ya da istek yolda
 * düşerse kayıt bu cihazda kuyruğa alınır ve bağlantı gelince gönderilir
 * (bkz. `offline.ts`).
 */

import { useState, type FormEvent } from "react";

import { api, type Expense } from "../api";
import { longDate, minorToInput } from "../format";
import { errorMessage } from "../hooks";
import { discard, enqueue, isNetworkError, type QueuedEntry } from "../offline";
import { Icon } from "./icons";
import { Card, ConfirmButton } from "./ui";

export type Draft = {
  amount: string;
  description: string;
  categoryId: number | null;
  transactionDate?: string;
  /** Kuyruktan forma aktarılan kaydın anahtarı; kaydedilince kuyruktan silinir. */
  queueRef?: string;
};

export function QuickEntry({
  onSaved,
  onDraft,
}: {
  /** Verilmezse (çevrimdışı açılış) her kayıt doğrudan kuyruğa yazılır. */
  onSaved?: (expense: Expense) => void;
  onDraft?: (draft: Draft) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState<string | null>(null);

  const queue = (value: string) => {
    enqueue(value);
    setQueued(value);
    setText("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setError(null);
    setQueued(null);
    try {
      if (!onSaved || navigator.onLine === false) {
        queue(value);
        return;
      }
      setBusy(true);
      const result = await api.quickEntry(value);
      if (result.expense) {
        onSaved(result.expense);
        return;
      }
      onDraft?.({
        amount: minorToInput(result.amount_minor ?? 0),
        description: result.description ?? "",
        categoryId: result.suggested_category_id,
      });
      setText("");
    } catch (cause: unknown) {
      if (isNetworkError(cause)) {
        try {
          queue(value);
        } catch (storageError: unknown) {
          setError(errorMessage(storageError));
        }
      } else {
        setError(errorMessage(cause));
      }
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
          Tutarı ve kategoriyi yazın; harcama bugünün tarihiyle nakit olarak kaydedilir. #kisisel
          yazarsanız ortak gider olarak sayılmaz. İnternet yoksa kayıt bu cihazda bekler ve
          bağlantı gelince gönderilir.
        </span>
        {queued && (
          <div className="alert info" role="status">
            İnternet bağlantısı yok. “{queued}” bu cihazda sıraya alındı; bağlantı gelince
            kaydedilecek.
          </div>
        )}
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
      </form>
    </Card>
  );
}

const STATE_LABELS: Record<QueuedEntry["state"], string> = {
  pending: "Gönderilmeyi bekliyor",
  needs_category: "Kategori seçilmeli",
  failed: "Kaydedilemedi",
};

/** Bu cihazda bekleyen çevrimdışı kayıtlar. */
export function QueueList({
  items,
  onComplete,
  onRetry,
}: {
  items: QueuedEntry[];
  /** Kategori gereken kaydı forma aktarır. Çevrimdışı açılışta verilmez. */
  onComplete?: (draft: Draft) => void;
  onRetry?: () => void;
}) {
  if (items.length === 0) return null;
  const pending = items.some((item) => item.state === "pending");

  return (
    <Card
      title="Bu cihazda bekleyen harcamalar"
      action={
        pending && onRetry ? (
          <button type="button" className="btn ghost sm" onClick={onRetry}>
            <Icon name="repeat" size={16} />
            Şimdi gönder
          </button>
        ) : undefined
      }
      flush
    >
      <div className="list">
        {items.map((item) => (
          <div className="list-item" key={item.ref}>
            <span className="list-main">
              <span className="list-title">{item.text}</span>
              <span className="list-sub">
                {longDate(item.date)} · {STATE_LABELS[item.state]}
                {item.error ? ` · ${item.error}` : ""}
              </span>
            </span>
            {item.state !== "pending" && onComplete && (
              <button
                type="button"
                className="btn secondary sm"
                onClick={() =>
                  onComplete({
                    amount:
                      item.amountMinor !== undefined && item.amountMinor !== null
                        ? minorToInput(item.amountMinor)
                        : "",
                    description: item.description ?? item.text,
                    categoryId: item.suggestedCategoryId ?? null,
                    transactionDate: item.date,
                    queueRef: item.ref,
                  })
                }
              >
                Tamamla
              </button>
            )}
            <ConfirmButton
              label=""
              icon="trash"
              className="icon-btn"
              confirmLabel="Sil"
              onConfirm={() => discard(item.ref)}
            />
          </div>
        ))}
      </div>
    </Card>
  );
}
