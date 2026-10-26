/**
 * Sunucu ile iletişim.
 *
 * Adresler **göreli**dir. Home Assistant Ingress sayfayı bir yol önekinin
 * altında sunar ve isteği uygulamaya iletirken bu öneki kaldırır; göreli adres
 * her iki tarafta da doğru çözülür. Mutlak `/api/...` kullanılırsa Ingress
 * altında 404 alınır.
 *
 * Kimlik için istemci başlık eklemez: web sitesinde tarayıcı oturum çerezini
 * kendiliğinden gönderir, Home Assistant panelinde başlığı HA kendisi koyar.
 */

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
  group_name: string | null;
  rollover: boolean;
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

export type AuthSource = "session" | "ingress";

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

export interface QuickEntryResult {
  /** Doluysa harcama kaydedildi. */
  expense: Expense | null;
  amount_minor: number | null;
  description: string | null;
  candidate_ids: number[];
  /** Kategori yazılmadıysa geçmiş kayıtlardan önerilen kategori. */
  suggested_category_id: number | null;
}

export interface SavingsGoal {
  id: number;
  name: string;
  target: Money;
  saved: Money;
  remaining: Money;
  target_date: string;
  months_left: number;
  monthly_required: Money;
  ratio: number;
  is_complete: boolean;
  is_overdue: boolean;
}

export interface SavingsOverview {
  goals: SavingsGoal[];
  /** Tüm hedefler için bu ay ayrılması gereken toplam. */
  monthly_required: Money;
  /** Bu ayın nakit durumunda kalan; gelir girilmemişse boş. */
  month_remaining: Money | null;
  /** Bu ayın kalanı hedeflere yetiyor mu; karşılaştırılamıyorsa boş. */
  covers: boolean | null;
}

export interface SavingsGoalInput {
  name: string;
  target_minor: number;
  target_date: string;
  saved_minor?: number;
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
  people: UserSummary[];
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
  owner_user_id: number | null;
  owner_name: string | null;
  tags: string[];
  has_receipt: boolean;
  installments: Installment[];
  splits: Split[];
}

export interface Split {
  category_id: number;
  category_name: string;
  category_emoji: string;
  amount: Money;
  note: string | null;
}

export interface SplitInput {
  category_id: number;
  amount: string;
  note: string | null;
}

export interface ExpenseInput {
  payment_method_id: number;
  category_id: number;
  transaction_date: string;
  amount: string;
  installment_count: number;
  description: string | null;
  is_shared: boolean;
  owner_user_id: number | null;
  /** İki veya daha fazla parça varsa harcama bölünür; boş liste bölmeyi kaldırır. */
  splits?: SplitInput[];
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
  group_name?: string;
  rollover?: boolean;
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

export interface PersonalBudget {
  user_id: number;
  name: string;
  year: number;
  budget: Money | null;
  spent: Money;
  remaining: Money | null;
  ratio: number;
  is_exceeded: boolean;
  expense_count: number;
  year_elapsed_ratio: number;
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
  carry_in: Money;
  available: Money | null;
  group_name: string | null;
  rollover: boolean;
}

export interface TargetSuggestion {
  category_id: number;
  name: string;
  emoji: string;
  group_name: string | null;
  current: Money | null;
  average: Money;
  suggested: Money | null;
  months: number;
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
// Kurallar, toplu islemler, ice aktarma, mutabakat, hesaplar, takvim
// ---------------------------------------------------------------------------

export type MatchType = "contains" | "equals" | "starts_with";

export interface Rule {
  id: number;
  pattern: string;
  match_type: MatchType;
  set_category_id: number | null;
  set_payment_method_id: number | null;
  set_description: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface RuleInput {
  pattern: string;
  match_type: MatchType;
  set_category_id?: number | null;
  set_payment_method_id?: number | null;
  set_description?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface RuleTest {
  category_id: number | null;
  payment_method_id: number | null;
  description: string | null;
  rule_ids: number[];
}

export interface PreviousValues {
  expense_id: number;
  category_id: number;
  description: string | null;
  is_shared: boolean;
  owner_user_id: number | null;
}

export interface BulkResult {
  changed: number[];
  skipped: Record<string, string>;
  /** Geri almak için aynen geri gönderilir. */
  previous: PreviousValues[];
}

export interface BulkChanges {
  category_id?: number;
  is_shared?: boolean;
  owner_user_id?: number;
  add_tag?: string;
  remove_tag?: string;
}

export interface DescriptionGroup {
  key: string;
  sample: string;
  count: number;
  total: Money;
}

export interface ColumnMapping {
  date_column: number;
  description_column: number;
  amount_column: number;
  first_row: number;
}

export type ImportSign = "auto" | "negative" | "positive";

export interface ImportPreviewRow {
  index: number;
  transaction_date: string | null;
  description: string;
  amount: Money;
  category_id: number | null;
  category_source: "rule" | "history" | "default" | null;
  payment_method_id: number | null;
  installment_count: number;
  installment_current: number | null;
  duplicate_of: string | null;
  skip_reason: "opposite_sign" | "zero" | "unreadable" | null;
  selected: boolean;
  note: string | null;
}

export interface ImportPreview {
  delimiter: string;
  mapping: ColumnMapping;
  sign: ImportSign;
  columns: string[];
  rows: ImportPreviewRow[];
}

export interface ImportRow {
  transaction_date: string;
  description: string | null;
  amount_minor: number;
  category_id: number;
  payment_method_id: number;
  installment_count: number;
  is_shared: boolean;
}

export interface ReconcileSummary {
  statement_date: string;
  due_date: string;
  ours_total: Money;
  line_count: number;
  cleared_count: number;
  bank_total: Money | null;
  difference: Money | null;
  is_reconciled: boolean;
  changed_since: boolean;
}

export interface ReconcileLine {
  kind: "installment" | "refund";
  id: number;
  expense_id: number;
  public_id: string;
  description: string | null;
  transaction_date: string;
  amount: Money;
  installment_number: number | null;
  installment_count: number | null;
  cleared: boolean;
}

export interface ReconcileDetail {
  summary: ReconcileSummary;
  lines: ReconcileLine[];
  cleared_total: Money;
  note: string | null;
}

export type AccountKind = "bank" | "cash" | "savings" | "investment" | "other";

export interface Account {
  id: number;
  name: string;
  kind: AccountKind;
  is_active: boolean;
  notes: string | null;
  balance: Money;
  last_balance_date: string | null;
}

export interface NetWorthPoint {
  when: string;
  assets: Money;
  card_debt: Money;
  net: Money;
}

export interface AccountsOverview {
  accounts: Account[];
  today: NetWorthPoint;
  history: NetWorthPoint[];
}

export interface AccountEntry {
  id: number;
  account_id: number;
  entry_date: string;
  kind: "balance" | "transfer" | "adjustment";
  amount: Money;
  transfer_group: string | null;
  payment_method_id: number | null;
  note: string | null;
}

export type EventKind = "recurring" | "statement" | "card_due" | "savings_goal";

export interface UpcomingEvent {
  when: string;
  kind: EventKind;
  title: string;
  amount: Money | null;
  detail: string | null;
  payment_method_id: number | null;
}

export interface CategoryMatrix {
  year: number;
  rows: {
    category_id: number;
    name: string;
    emoji: string;
    group_name: string;
    months: Money[];
    total: Money;
  }[];
  month_totals: Money[];
  total: Money;
}

export interface FlowMonth {
  year: number;
  month: number;
  income: Money;
  spending: Money;
  net: Money;
}

export interface DailySpending {
  year: number;
  month: number;
  days: Money[];
  total: Money;
}

export interface FlowNode {
  name: string;
  amount: Money;
  categories: { name: string; amount: Money }[];
}

export interface MoneyFlow {
  year: number;
  month: number;
  sources: FlowNode[];
  targets: FlowNode[];
  income: Money;
  spending: Money;
  remaining: Money;
}

export interface DashboardData {
  position: MonthlyPosition;
  forecast: MonthForecast;
  spending: MonthlySpending;
  shared_spending: MonthlySpending;
  budgets: BudgetStatus[];
  cards: CardUsage[];
  statements: Statement[];
  recent: SearchResult;
  upcoming: UpcomingEvent[];
  personal_budgets: PersonalBudget[];
  savings_goals: SavingsOverview;
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
const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
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
  /** `extra`: çevrimdışı kuyruktan gelen kaydın günü ve tekil anahtarı. */
  quickEntry: (text: string, extra?: { transaction_date?: string; client_ref?: string }) =>
    post<QuickEntryResult>("expenses/quick", { text, ...extra }),

  // Fis fotografi
  uploadReceipt: (expenseId: number, image: Blob) =>
    request<void>(`expenses/${expenseId}/receipt`, {
      method: "PUT",
      body: image,
      headers: { "Content-Type": image.type || "image/jpeg" },
    }),
  deleteReceipt: (expenseId: number) => remove(`expenses/${expenseId}/receipt`),
  /** `version` degisince tarayici fotografi yeniden ister. */
  receiptUrl: (expenseId: number, version: number) =>
    `${API_BASE}/expenses/${expenseId}/receipt?v=${version}`,

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
  /** Açıklamaya göre geçmiş kayıtlardan kategori önerisi. Hiçbir şey kaydetmez. */
  suggestCategory: (description: string) =>
    get<{ category_id: number | null }>("categories/suggest", { description }),
  addCategory: (payload: CategoryInput) => post<Category>("categories", payload),
  updateCategory: (id: number, changes: Partial<CategoryInput>) =>
    patch<Category>(`categories/${id}`, changes),
  deleteCategory: (id: number) => remove(`categories/${id}`),

  // Raporlar
  dashboard: () => get<DashboardData>("reports/dashboard"),
  spending: (query: YearMonthQuery & { owner?: string }) =>
    get<MonthlySpending>("reports/spending/monthly", query),
  personalBudgets: (year?: number) => get<PersonalBudget[]>("reports/personal-budgets", { year }),
  setPersonalBudget: (userId: number, year: number, amount: string | null) =>
    request<PersonalBudget[]>(`personal-budgets/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ year, amount }),
    }),
  position: () => get<MonthlyPosition>("reports/position"),
  budgets: (query: YearMonthQuery) => get<BudgetStatus[]>("reports/budgets", query),
  cards: () => get<CardUsage[]>("reports/cards"),
  forecast: () => get<MonthForecast>("reports/forecast"),
  yearly: (year?: number) => get<YearComparison>("reports/yearly", { year }),
  tags: (query: YearMonthQuery) => get<TagTotal[]>("reports/tags", query),
  statements: () => get<Statement[]>("reports/cashflow/statements"),
  upcoming: (months: number, basis: ObligationBasis) =>
    get<Obligations>("reports/cashflow/upcoming", { months, basis }),
  installmentPlans: () => get<InstallmentPlan[]>("reports/installments"),

  // Birikim hedefleri
  savingsGoals: () => get<SavingsOverview>("savings-goals"),
  addSavingsGoal: (payload: SavingsGoalInput) => post<SavingsOverview>("savings-goals", payload),
  updateSavingsGoal: (id: number, changes: Partial<Omit<SavingsGoalInput, "saved_minor">>) =>
    patch<SavingsOverview>(`savings-goals/${id}`, changes),
  depositSavings: (id: number, amount_minor: number) =>
    post<SavingsOverview>(`savings-goals/${id}/deposits`, { amount_minor }),
  deleteSavingsGoal: (id: number) => remove(`savings-goals/${id}`),

  // Butce hedefleri
  budgetSuggestions: (months: number) =>
    get<TargetSuggestion[]>("reports/budgets/suggestions", { months }),
  applyBudgets: (items: { category_id: number; monthly_budget_minor: number }[]) =>
    post<BudgetStatus[]>("budgets/apply", { items }),

  // Ayrintili raporlar ve takvim
  upcomingEvents: (days: number) => get<UpcomingEvent[]>("reports/upcoming", { days }),
  categoryMatrix: (year: number) => get<CategoryMatrix>("reports/category-matrix", { year }),
  cashflowHistory: (months: number) => get<FlowMonth[]>("reports/cashflow-history", { months }),
  daily: (query: YearMonthQuery) => get<DailySpending>("reports/daily", query),
  flow: (query: YearMonthQuery) => get<MoneyFlow>("reports/flow", query),

  // Geri alma ve toplu islemler
  restoreExpense: (id: number) => post<Expense>(`expenses/${id}/restore`),
  bulkUpdate: (ids: number[], changes: BulkChanges) =>
    post<BulkResult>("expenses/bulk/update", { ids, ...changes }),
  bulkRevert: (items: PreviousValues[]) => post<BulkResult>("expenses/bulk/revert", { items }),
  bulkDelete: (ids: number[]) => post<BulkResult>("expenses/bulk/delete", { ids }),
  bulkRestore: (ids: number[]) => post<BulkResult>("expenses/bulk/restore", { ids }),

  // Kurallar ve aciklamalar
  rules: () => get<Rule[]>("rules"),
  addRule: (payload: RuleInput) => post<Rule>("rules", payload),
  updateRule: (id: number, changes: Partial<RuleInput> & { clear?: string[] }) =>
    patch<Rule>(`rules/${id}`, changes),
  deleteRule: (id: number) => remove(`rules/${id}`),
  testRules: (description: string) => get<RuleTest>("rules/test", { description }),
  previewRule: (id: number) => get<number[]>(`rules/${id}/preview`),
  applyRule: (id: number) => post<BulkResult>(`rules/${id}/apply`),
  descriptions: (q: string) => get<DescriptionGroup[]>("descriptions", { q }),
  mergeDescriptions: (keys: string[], target: string, create_rule: boolean) =>
    post<BulkResult>("descriptions/merge", { keys, target, create_rule }),

  // Ice aktarma
  importPreview: (payload: {
    text: string;
    payment_method_id: number;
    default_category_id: number | null;
    sign: ImportSign;
    mapping: ColumnMapping | null;
  }) => post<ImportPreview>("import/preview", payload),
  importCommit: (rows: ImportRow[]) =>
    post<{ created: number; total: Money; expense_ids: number[] }>("import/commit", { rows }),

  // Mutabakat
  reconcileStatements: (cardId: number) => get<ReconcileSummary[]>(`reconcile/${cardId}`),
  reconcileDetail: (cardId: number, statementDate: string) =>
    get<ReconcileDetail>(`reconcile/${cardId}/${statementDate}`),
  reconcileMark: (cardId: number, statementDate: string, ids: number[], cleared: boolean) =>
    post<ReconcileDetail>(`reconcile/${cardId}/${statementDate}/cleared`, {
      installment_ids: ids,
      cleared,
    }),
  reconcileSave: (cardId: number, statementDate: string, bankTotalMinor: number, note: string | null) =>
    put<ReconcileDetail>(`reconcile/${cardId}/${statementDate}`, {
      bank_total_minor: bankTotalMinor,
      note,
    }),
  reconcileForget: (cardId: number, statementDate: string) =>
    remove(`reconcile/${cardId}/${statementDate}`),

  // Hesaplar
  accounts: () => get<AccountsOverview>("accounts"),
  addAccount: (payload: {
    name: string;
    kind: AccountKind;
    opening_balance_minor: number | null;
    opening_date: string | null;
    notes: string | null;
  }) => post<AccountsOverview>("accounts", payload),
  updateAccount: (
    id: number,
    changes: { name?: string; kind?: AccountKind; is_active?: boolean; notes?: string },
  ) => patch<AccountsOverview>(`accounts/${id}`, changes),
  deleteAccount: (id: number) => remove(`accounts/${id}`),
  accountEntries: (id: number) => get<AccountEntry[]>(`accounts/${id}/entries`),
  setBalance: (id: number, balance_minor: number, entry_date: string, note: string | null) =>
    post<AccountEntry>(`accounts/${id}/balance`, { balance_minor, entry_date, note }),
  addAdjustment: (id: number, amount_minor: number, entry_date: string, note: string | null) =>
    post<AccountEntry>(`accounts/${id}/adjustments`, { amount_minor, entry_date, note }),
  transfer: (payload: {
    from_account_id: number;
    to_account_id: number | null;
    payment_method_id: number | null;
    amount_minor: number;
    entry_date: string;
    note: string | null;
  }) => post<AccountEntry[]>("transfers", payload),
  deleteAccountEntry: (id: number) => remove(`account-entries/${id}`),

  // Disa aktarma
  exportCsv: (kind: "expenses" | "incomes", query: YearMonthQuery, filename: string) =>
    download(withQuery(`export/${kind}.csv`, query), filename),
};
