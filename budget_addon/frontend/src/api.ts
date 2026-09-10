/**
 * Sunucu ile iletişim.
 *
 * Adresler **göreli**dir. Home Assistant Ingress sayfayı bir yol önekinin
 * altında sunar ve isteği uygulamaya iletirken bu öneki kaldırır; göreli adres
 * her iki tarafta da doğru çözülür. Mutlak `/api/...` kullanılırsa Ingress
 * altında 404 alınır.
 *
 * Kimlik bağlama göre farklı yoldan gider: web sitesinde tarayıcı oturum
 * çerezini kendiliğinden ekler, Telegram içinde imzalı `initData` başlığı
 * gönderilir, Home Assistant panelinde başlığı HA kendisi koyar.
 */

import { telegram } from "./telegram";

const API_BASE = "api";

/** Oturum düştüğünde yayınlanır; uygulama giriş ekranına döner. */
export const AUTH_REQUIRED_EVENT = "butce:auth-required";

/** Bildirim okununca veya yenisi oluşunca yayınlanır; menüdeki sayı tazelenir. */
export const NOTIFICATIONS_CHANGED_EVENT = "butce:notifications-changed";

export interface Money {
  minor: number;
  formatted: string;
}

export interface Category {
  id: number;
  name: string;
  emoji: string;
  is_active: boolean;
  monthly_budget_minor: number | null;
}

export type PaymentMethodType = "cash" | "credit_card";

export interface PaymentMethod {
  id: number;
  name: string;
  type: PaymentMethodType;
  is_active: boolean;
  statement_day: number | null;
  due_offset_days: number;
  cutoff_inclusive: boolean;
  owner_user_id: number | null;
}

export interface UserSummary {
  id: number;
  display_name: string;
  role: string;
}

export type AuthSource = "session" | "ingress" | "telegram" | "dev";

export interface Me extends UserSummary {
  username: string | null;
  is_admin: boolean;
  reminders_enabled: boolean;
  auth_source: AuthSource;
}

export interface SetupPerson {
  id: number;
  display_name: string;
}

export interface SetupInput {
  code: string;
  user_id: number | null;
  display_name: string | null;
  username: string;
  password: string;
}

export interface AdminUser {
  id: number;
  display_name: string;
  username: string | null;
  is_admin: boolean;
  is_active: boolean;
  has_login: boolean;
}

export interface AppNotification {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  is_read: boolean;
}

export interface NotificationList {
  unread: number;
  items: AppNotification[];
}

export interface NotificationSettings {
  reminders_enabled: boolean;
  reminder_hour: number;
  email: string | null;
  email_notifications: boolean;
  email_available: boolean;
  push_public_key: string;
  push_devices: number;
}

export interface NotificationTestResult {
  email: "sent" | "skipped" | "failed";
  push_sent: number;
  push_devices: number;
}

export interface AdminUserInput {
  display_name: string;
  username: string;
  password: string;
  is_admin: boolean;
  is_active: boolean;
}

export interface Bootstrap {
  user: UserSummary;
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

export interface Installment {
  number: number;
  count: number;
  amount: Money;
  statement_date: string;
  due_date: string;
  status: string;
}

export interface Expense {
  id: number;
  public_id: string;
  created_by: string;
  category: Category;
  payment_method_id: number | null;
  payment_method_name: string;
  transaction_date: string;
  total: Money;
  installment_count: number;
  description: string | null;
  is_shared: boolean;
  tags: string[];
  has_receipt: boolean;
  installments: Installment[];
}

export interface ExpenseInput {
  payment_method_id: number;
  category_id: number;
  transaction_date: string;
  amount: string;
  installment_count: number;
  description: string | null;
  is_shared: boolean;
}

export interface SearchFilters {
  text?: string;
  date_from?: string;
  date_to?: string;
  category_id?: number | null;
  payment_method_id?: number | null;
  created_by_user_id?: number | null;
  min_amount_minor?: number | null;
  max_amount_minor?: number | null;
  page?: number;
  page_size?: number;
}

export interface SearchResult {
  items: Expense[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
}

export interface Refund {
  id: number;
  expense_id: number;
  amount: Money;
  refund_date: string;
  statement_date: string | null;
  due_date: string | null;
  notes: string | null;
}

export interface Income {
  id: number;
  source: string;
  amount: Money;
  received_date: string;
  notes: string | null;
}

export interface RecurringExpense {
  id: number;
  name: string;
  category_id: number;
  payment_method_id: number;
  amount: Money;
  day_of_month: number;
  start_date: string;
  notes: string | null;
  is_active: boolean;
}

export interface RecurringInput {
  name: string;
  category_id: number;
  payment_method_id: number;
  amount_minor: number;
  day_of_month: number;
  notes: string | null;
  is_active?: boolean;
}

export interface PaymentMethodInput {
  name: string;
  type?: PaymentMethodType;
  statement_day?: number | null;
  due_offset_days?: number;
  cutoff_inclusive?: boolean;
  owner_user_id?: number | null;
  credit_limit_minor?: number | null;
  is_active?: boolean;
}

export interface CategoryInput {
  name: string;
  emoji: string;
  monthly_budget_minor?: number | null;
  sort_order?: number;
  is_active?: boolean;
}

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
  largest_expense: Expense | null;
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

export interface TagTotal {
  tag: string;
  total: Money;
  transaction_count: number;
}

export interface Statement {
  payment_method_id: number;
  payment_method_name: string;
  statement_date: string;
  due_date: string;
  total: Money;
  installment_count: number;
}

export interface InstallmentPlan {
  expense_id: number;
  public_id: string;
  description: string | null;
  category_name: string;
  payment_method_name: string;
  total: Money;
  remaining: Money;
  monthly: Money;
  position: string;
}

export type ObligationBasis = "statement" | "due";

export interface Obligations {
  basis: ObligationBasis;
  basis_label: string;
  months: { year: number; month: number; total: Money; installment_count: number }[];
}

// ---------------------------------------------------------------------------
// Tasima
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/**
 * Kimlik başlığını bağlama göre seçer.
 *
 * Telegram içinde çalışıyorsak imzalı `initData` gönderilir. Home Assistant
 * Ingress altında ve web sitesinde istemcinin başlık eklemesi gerekmez.
 * Geliştirme başlığı yalnızca yerelde anlamlıdır.
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

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;
    params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/${path}`, {
      credentials: "same-origin",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edin.", 0);
  }

  if (response.ok) return response;

  let detail = "İşlem tamamlanamadı. Lütfen tekrar deneyin.";
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // Govde okunamadiysa genel mesaj kalir.
  }
  if (response.status === 401) {
    window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  } else if (response.status === 403) {
    detail = "Bu uygulamayı kullanma yetkiniz bulunmuyor.";
  }
  throw new ApiError(detail, response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T>(path: string, query?: Query) => request<T>(withQuery(path, query));
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const remove = (path: string) => request<void>(path, { method: "DELETE" });

async function download(path: string, filename: string): Promise<void> {
  const response = await send(path, { headers: { Accept: "text/csv" } });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

type YearMonthQuery = { year?: number; month?: number };

export const api = {
  // Oturum
  me: () => get<Me>("me"),
  login: (username: string, password: string, remember: boolean) =>
    post<Me>("auth/login", { username, password, remember }),
  logout: () => post<void>("auth/logout"),
  updateMe: (changes: { reminders_enabled?: boolean }) => patch<Me>("me", changes),
  changePassword: (current_password: string, new_password: string) =>
    post<Me>("me/password", { current_password, new_password }),
  users: () => get<UserSummary[]>("users"),

  // Ilk kurulum
  setupStatus: () => get<{ required: boolean }>("setup"),
  verifySetup: (code: string) => post<SetupPerson[]>("setup/verify", { code }),
  completeSetup: (payload: SetupInput) => post<Me>("setup", payload),

  // Kisiler (yonetici)
  adminUsers: () => get<AdminUser[]>("admin/users"),
  addUser: (payload: Omit<AdminUserInput, "is_active">) => post<AdminUser>("admin/users", payload),
  updateUser: (id: number, changes: Partial<AdminUserInput>) =>
    patch<AdminUser>(`admin/users/${id}`, changes),

  // Bildirimler
  notifications: (limit: number) => get<NotificationList>("notifications", { limit }),
  markNotificationsRead: (ids?: number[]) =>
    post<{ unread: number }>("notifications/read", { ids: ids ?? null }),
  notificationSettings: () => get<NotificationSettings>("notifications/settings"),
  updateNotificationSettings: (changes: {
    reminders_enabled?: boolean;
    email?: string;
    email_notifications?: boolean;
  }) => patch<NotificationSettings>("notifications/settings", changes),
  testNotification: () => post<NotificationTestResult>("notifications/test"),
  subscribePush: (subscription: PushSubscriptionJSON) =>
    post<void>("push/subscriptions", subscription),
  unsubscribePush: (endpoint: string) => post<void>("push/unsubscribe", { endpoint }),
  bootstrap: () => get<Bootstrap>("bootstrap"),

  // Harcamalar
  preview: (payload: {
    payment_method_id: number;
    transaction_date: string;
    amount: string;
    installment_count: number;
  }) => post<SchedulePreview>("expenses/preview", payload),
  createExpense: (payload: ExpenseInput) => post<Expense>("expenses", payload),
  getExpense: (id: number) => get<Expense>(`expenses/${id}`),
  updateExpense: (id: number, changes: Partial<ExpenseInput>) =>
    patch<Expense>(`expenses/${id}`, changes),
  deleteExpense: (id: number) => remove(`expenses/${id}`),
  searchExpenses: (filters: SearchFilters) => get<SearchResult>("expenses", { ...filters }),

  // Iadeler
  refunds: (expenseId: number) => get<Refund[]>(`expenses/${expenseId}/refunds`),
  addRefund: (
    expenseId: number,
    payload: { amount_minor: number; refund_date: string; notes: string | null },
  ) => post<Refund>(`expenses/${expenseId}/refunds`, payload),
  deleteRefund: (id: number) => remove(`refunds/${id}`),

  // Gelirler
  incomes: (query: YearMonthQuery) => get<Income[]>("incomes", query),
  addIncome: (payload: {
    amount_minor: number;
    received_date: string;
    source: string;
    notes: string | null;
  }) => post<Income>("incomes", payload),
  deleteIncome: (id: number) => remove(`incomes/${id}`),

  // Sabit giderler
  recurring: () => get<RecurringExpense[]>("recurring", { include_inactive: true }),
  addRecurring: (payload: RecurringInput) => post<RecurringExpense>("recurring", payload),
  updateRecurring: (id: number, changes: Partial<RecurringInput>) =>
    patch<RecurringExpense>(`recurring/${id}`, changes),
  deleteRecurring: (id: number) => remove(`recurring/${id}`),

  // Ayarlar
  paymentMethods: () => get<PaymentMethod[]>("payment-methods", { include_inactive: true }),
  addPaymentMethod: (payload: PaymentMethodInput) =>
    post<PaymentMethod>("payment-methods", payload),
  updatePaymentMethod: (id: number, changes: Partial<PaymentMethodInput>) =>
    patch<PaymentMethod>(`payment-methods/${id}`, changes),
  deletePaymentMethod: (id: number) => remove(`payment-methods/${id}`),
  categories: () => get<Category[]>("categories", { include_inactive: true }),
  addCategory: (payload: CategoryInput) => post<Category>("categories", payload),
  updateCategory: (id: number, changes: Partial<CategoryInput>) =>
    patch<Category>(`categories/${id}`, changes),
  deleteCategory: (id: number) => remove(`categories/${id}`),

  // Raporlar
  spending: (query: YearMonthQuery) => get<MonthlySpending>("reports/spending/monthly", query),
  position: () => get<MonthlyPosition>("reports/position"),
  budgets: (query: YearMonthQuery) => get<BudgetStatus[]>("reports/budgets", query),
  cards: () => get<CardUsage[]>("reports/cards"),
  forecast: () => get<MonthForecast>("reports/forecast"),
  settlement: (query: YearMonthQuery) => get<Settlement>("reports/settlement", query),
  yearly: (year?: number) => get<YearComparison>("reports/yearly", { year }),
  tags: (query: YearMonthQuery) => get<TagTotal[]>("reports/tags", query),
  statements: () => get<Statement[]>("reports/cashflow/statements"),
  upcoming: (months: number, basis: ObligationBasis) =>
    get<Obligations>("reports/cashflow/upcoming", { months, basis }),
  installmentPlans: () => get<InstallmentPlan[]>("reports/installments"),

  // Disa aktarma
  exportCsv: (kind: "expenses" | "incomes", query: YearMonthQuery, filename: string) =>
    download(withQuery(`export/${kind}.csv`, query), filename),
};
