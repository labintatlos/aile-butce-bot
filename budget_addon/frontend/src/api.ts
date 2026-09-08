/**
 * Sunucu ile iletişim.
 *
 * Adresler **göreli**dir. Home Assistant Ingress sayfayı bir yol önekinin
 * altında sunar ve isteği uygulamaya iletirken bu öneki kaldırır; göreli adres
 * her iki tarafta da doğru çözülür. Mutlak `/api/...` kullanılırsa Ingress
 * altında 404 alınır.
 */

import { telegram } from "./telegram";

const API_BASE = "api";

export interface Money {
  minor: number;
  formatted: string;
}

export interface Category {
  id: number;
  name: string;
  emoji: string;
  is_active: boolean;
}

export interface PaymentMethod {
  id: number;
  name: string;
  type: "cash" | "credit_card";
  is_active: boolean;
  statement_day: number | null;
  due_day: number | null;
}

export interface Bootstrap {
  user: { id: number; display_name: string; role: string };
  categories: Category[];
  payment_methods: PaymentMethod[];
  today: string;
  currency: string;
  max_installments: number;
}

export interface SchedulePreview {
  total: Money;
  installment_count: number;
  installment_amount: Money;
  first_statement_date: string | null;
  first_due_date: string | null;
  last_due_date: string | null;
  is_credit_card: boolean;
}

export interface Expense {
  id: number;
  public_id: string;
  created_by: string;
  category: Category;
  payment_method_name: string;
  transaction_date: string;
  total: Money;
  installment_count: number;
  description: string | null;
}

export class ApiError extends Error {}

/**
 * Kimlik başlığını bağlama göre seçer.
 *
 * Telegram içinde çalışıyorsak imzalı `initData` gönderilir. Home Assistant
 * Ingress altında kimliği HA kendi başlığıyla ekler ve istemcinin bir şey
 * göndermesi gerekmez. Geliştirme başlığı yalnızca yerelde anlamlıdır.
 */
function authHeaders(): Record<string, string> {
  const initData = telegram()?.initData;
  if (initData) {
    return { Authorization: `tma ${initData}` };
  }
  const devUser = import.meta.env.VITE_DEV_TELEGRAM_USER_ID;
  if (devUser) {
    return { "X-Dev-Telegram-User-Id": String(devUser) };
  }
  return {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}/${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = "İşlem tamamlanamadı. Lütfen tekrar deneyin.";
    if (response.status === 401 || response.status === 403) {
      detail = "Bu uygulamayı kullanma yetkiniz bulunmuyor.";
    } else {
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // Govde okunamadiysa genel mesaj kalir.
      }
    }
    throw new ApiError(detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  bootstrap: () => request<Bootstrap>("bootstrap"),

  preview: (payload: {
    payment_method_id: number;
    transaction_date: string;
    amount: string;
    installment_count: number;
  }) =>
    request<SchedulePreview>("expenses/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createExpense: (payload: {
    payment_method_id: number;
    category_id: number;
    transaction_date: string;
    amount: string;
    installment_count: number;
    description: string | null;
  }) =>
    request<Expense>("expenses", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
