/**
 * Çevrimdışı hızlı giriş kuyruğu.
 *
 * Bağlantı yokken yazılan "500 market" bu cihazda saklanır ve bağlantı gelince
 * sunucuya gönderilir. Kurallar:
 *
 * - Kayıt **girildiği günün** tarihiyle gönderilir, gönderildiği günün değil.
 * - Her kaydın tekil bir anahtarı (`ref`) vardır. Yanıt yolda kaybolup aynı
 *   kayıt yeniden gönderilirse sunucu ikinci bir harcama açmaz.
 * - Kategorisi tek başına anlaşılamayan kayıt sessizce kaydedilmez; "kategori
 *   seçilmeli" olarak bekler ve kişi formdan tamamlar.
 *
 * Kuyruk tarayıcının yerel deposundadır, yani yalnızca bu cihazda durur.
 * Depolama kapalıysa (gizli sekme vb.) kuyruk çalışmaz ve kişiye söylenir.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";

const STORAGE_KEY = "aile-butce-kuyruk";
const CHANGED_EVENT = "butce:offline-queue-changed";
const RETRY_MS = 30_000;

export type QueueState = "pending" | "needs_category" | "failed";

export interface QueuedEntry {
  ref: string;
  text: string;
  /** Girildiği gün (cihazın yerel tarihi, YYYY-AA-GG). */
  date: string;
  createdAt: string;
  state: QueueState;
  amountMinor?: number | null;
  description?: string | null;
  suggestedCategoryId?: number | null;
  error?: string;
}

function read(): QueuedEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as QueuedEntry[]) : [];
  } catch {
    return [];
  }
}

function write(items: QueuedEntry[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

function update(ref: string, changes: Partial<QueuedEntry> | null): void {
  const items = read();
  write(
    changes === null
      ? items.filter((item) => item.ref !== ref)
      : items.map((item) => (item.ref === ref ? { ...item, ...changes } : item)),
  );
}

function localDate(moment = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`;
}

function newRef(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  // Eski tarayıcılar: zaman ve rastgele sayıdan yeterince tekil bir anahtar.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Bağlantı hatası mı? Sunucunun verdiği bir ret (422, 401) değil. */
export function isNetworkError(cause: unknown): boolean {
  return cause instanceof ApiError && cause.status === 0;
}

/** Kaydı kuyruğa yazar. Depolama kapalıysa hata fırlatır. */
export function enqueue(text: string): QueuedEntry {
  const entry: QueuedEntry = {
    ref: newRef(),
    text: text.trim(),
    date: localDate(),
    createdAt: new Date().toISOString(),
    state: "pending",
  };
  try {
    write([...read(), entry]);
  } catch {
    throw new Error(
      "Bu tarayıcıda çevrimdışı kayıt saklanamıyor (gizli sekme veya depolama kapalı).",
    );
  }
  return entry;
}

export function discard(ref: string): void {
  update(ref, null);
}

let flushing: Promise<number> | null = null;

/**
 * Bekleyen kayıtları sırayla gönderir; kaydedilen sayısını döndürür.
 *
 * Bağlantı yine yoksa ilk hatada durur, sıradakiler bir sonraki denemeye
 * kalır. Aynı anda iki gönderim başlamaz.
 */
export function flushQueue(): Promise<number> {
  if (flushing) return flushing;
  flushing = (async () => {
    let saved = 0;
    for (const item of read().filter((entry) => entry.state === "pending")) {
      try {
        const result = await api.quickEntry(item.text, {
          transaction_date: item.date,
          client_ref: item.ref,
        });
        if (result.expense) {
          update(item.ref, null);
          saved += 1;
        } else {
          update(item.ref, {
            state: "needs_category",
            amountMinor: result.amount_minor,
            description: result.description,
            suggestedCategoryId: result.suggested_category_id,
          });
        }
      } catch (cause: unknown) {
        if (isNetworkError(cause)) break;
        if (cause instanceof ApiError && cause.status === 401) break;
        update(item.ref, {
          state: "failed",
          error: cause instanceof Error ? cause.message : "Kaydedilemedi.",
        });
      }
    }
    return saved;
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}

/**
 * Kuyruğu izler ve bağlantı gelince, sekmeye dönülünce ve bekleyen kayıt
 * varken yarım dakikada bir gönderir.
 */
export function useOfflineQueue(onSaved?: (count: number) => void) {
  const [items, setItems] = useState<QueuedEntry[]>(read);

  const flush = useCallback(async () => {
    const saved = await flushQueue();
    if (saved > 0) onSaved?.(saved);
    return saved;
  }, [onSaved]);

  useEffect(() => {
    const refresh = () => setItems(read());
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) refresh();
    };
    window.addEventListener(CHANGED_EVENT, refresh);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(CHANGED_EVENT, refresh);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const pending = items.filter((item) => item.state === "pending").length;

  useEffect(() => {
    if (pending === 0) return;
    const attempt = () => {
      if (navigator.onLine !== false) void flush();
    };
    attempt();
    const timer = window.setInterval(attempt, RETRY_MS);
    window.addEventListener("online", attempt);
    window.addEventListener("focus", attempt);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("online", attempt);
      window.removeEventListener("focus", attempt);
    };
  }, [pending, flush]);

  return { items, pending, flush };
}
