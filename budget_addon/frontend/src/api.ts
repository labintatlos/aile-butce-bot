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

// ---------------------------------------------------------------------------
// Raporlar
// ---------------------------------------------------------------------------

export interface NamedTotal {
  id: number;
  name: string;
  emoji: string;
  total: Money;
  transaction_count: number;
}

export interface MonthlySpending {
  year: number;
  month: number;
  total: Money;
  transaction_count: number;
  cash_total: Money;
  card_total: Money;
  by_user: NamedTotal[];
  by_category: NamedTotal[];
}

export interface MonthlyPosition {
  year: number;
  month: number;
  income: Money;
  card_due: Money;
  cash_spent: Money;
  expected_recurring: Money;
  outflow: Money;
  remaining: Money;
}

export interface BudgetStatus {
  category_id: number;
  name: string;
  emoji: string;
  budget: Money;
  spent: Money;
  remaining: Money;
  ratio: number;
  is_exceeded: boolean;
}

export interface CardUsage {
  payment_method_id: number;
  name: string;
  credit_limit: Money | null;
  outstanding: Money;
  available: Money;
  ratio: number;
  is_over_limit: boolean;
}

export interface MonthForecast {
  year: number;
  month: number;
  days_elapsed: number;
  days_in_month: number;
  spent_so_far: Money;
  fixed: Money;
  variable_forecast: Money;
  total: Money;
  remaining: Money;
}

export interface PersonBalance {
  user_id: number;
  name: string;
  paid: Money;
  share: Money;
  balance: Money;
}

export interface Settlement {
  year: number;
  month: number;
  shared_total: Money;
  balances: PersonBalance[];
  is_even: boolean;
  transfer: Money;
  creditor_name: string | null;
  debtor_name: string | null;
}

export interface MonthComparison {
  month: number;
  this_year: Money;
  last_year: Money;
  change_percent: number | null;
}

export interface YearComparison {
  year: number;
  months: MonthComparison[];
  this_year_total: Money;
  last_year_total: Money;
}

/** Rapor ekranının ihtiyaç duyduğu her şey. */
export interface ReportBundle {
  spending: MonthlySpending;
  position: MonthlyPosition;
  budgets: BudgetStatus[];
  cards: CardUsage[];
  forecast: MonthForecast;
  settlement: Settlement;
  year: YearComparison;
}

export const reports = {
  /**
   * Rapor ekranının bütün verisini tek seferde çeker.
   *
   * İstekler paralel gönderilir: her biri küçüktür ve sırayla beklemek
   * ekranın açılışını gereksiz yere yavaşlatırdı.
   */
  load: async (): Promise<ReportBundle> => {
    const [spending, position, budgets, cards, forecast, settlement, year] =
      await Promise.all([
        request<MonthlySpending>("reports/spending/monthly"),
        request<MonthlyPosition>("reports/position"),
        request<BudgetStatus[]>("reports/budgets"),
        request<CardUsage[]>("reports/cards"),
        request<MonthForecast>("reports/forecast"),
        request<Settlement>("reports/settlement"),
        request<YearComparison>("reports/yearly"),
      ]);
    return { spending, position, budgets, cards, forecast, settlement, year };
  },
};
