/**
 * Uygulama kabuğu.
 *
 * Aynı arayüz iki bağlamda çalışır: web sitesi (kullanıcı adı ve şifre) ve
 * Home Assistant paneli. Açılışta `/api/me` sorulur;
 * kimlik bağlamdan geliyorsa doğrudan içeri girilir, gelmiyorsa giriş ekranı
 * gösterilir.
 *
 * Masaüstünde sol kenar çubuğu, telefonda alt gezinme çubuğu kullanılır.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  AUTH_REQUIRED_EVENT,
  NOTIFICATIONS_CHANGED_EVENT,
  type Bootstrap,
  type Me,
  type UserSummary,
} from "./api";
import { ExpenseForm } from "./components/ExpenseForm";
import { Icon, type IconName } from "./components/icons";
import { QueueList, QuickEntry } from "./components/QuickEntry";
import { ThemePicker } from "./components/ThemePicker";
import { Loading, Modal, ToastProvider, useToast } from "./components/ui";
import { authSourceLabel, initialOf, SessionContext, useSession, type Session } from "./context";
import { clearAsyncCache, errorMessage, useHashRoute, type Route } from "./hooks";
import { isNetworkError, useOfflineQueue } from "./offline";
import { Dashboard } from "./pages/Dashboard";
import { Expenses } from "./pages/Expenses";
import { Login } from "./pages/Login";
import { More } from "./pages/More";
import { NewExpense } from "./pages/NewExpense";
import { Settings } from "./pages/Settings";
import { Setup } from "./pages/Setup";
import { Upcoming } from "./pages/Upcoming";

const Reports = lazy(() => import("./pages/Reports").then((m) => ({ default: m.Reports })));
const Statements = lazy(() =>
  import("./pages/Statements").then((m) => ({ default: m.Statements })),
);
const Accounts = lazy(() => import("./pages/Accounts").then((m) => ({ default: m.Accounts })));
const Rules = lazy(() => import("./pages/Rules").then((m) => ({ default: m.Rules })));
const Recurring = lazy(() => import("./pages/Recurring").then((m) => ({ default: m.Recurring })));
const Incomes = lazy(() => import("./pages/Incomes").then((m) => ({ default: m.Incomes })));
const People = lazy(() => import("./pages/People").then((m) => ({ default: m.People })));
const Notifications = lazy(() =>
  import("./pages/Notifications").then((m) => ({ default: m.Notifications })),
);

type Phase =
  | { kind: "loading" }
  | { kind: "login" }
  | { kind: "setup" }
  | { kind: "failed"; message: string }
  | { kind: "offline" }
  | { kind: "ready"; me: Me; bootstrap: Bootstrap; users: UserSummary[] };

interface NavItem {
  route: Route;
  label: string;
  icon: IconName;
  admin?: boolean;
}

const NAV_GROUPS: readonly { title: string; items: readonly NavItem[] }[] = [
  {
    title: "GÜNLÜK",
    items: [
      { route: "ozet", label: "Özet", icon: "home" },
      { route: "harcamalar", label: "Harcamalar", icon: "list" },
      { route: "gelirler", label: "Gelirler", icon: "income" },
      { route: "raporlar", label: "Raporlar", icon: "chart" },
    ],
  },
  {
    title: "PLANLAMA & BANKA",
    items: [
      { route: "takvim", label: "Yaklaşanlar", icon: "calendar" },
      { route: "sabit", label: "Sabit Giderler", icon: "repeat" },
      { route: "hesaplar", label: "Hesaplar", icon: "bank" },
      { route: "aktar", label: "Ekstre", icon: "upload" },
    ],
  },
  {
    title: "SİSTEM",
    items: [
      { route: "kurallar", label: "Kurallar", icon: "wand" },
      { route: "bildirimler", label: "Bildirimler", icon: "bell" },
      { route: "ayarlar", label: "Ayarlar", icon: "settings" },
      { route: "kisiler", label: "Kişiler", icon: "users", admin: true },
    ],
  },
];

const MOBILE_NAV: readonly { route: Route; label: string; icon: IconName }[] = [
  { route: "ozet", label: "Özet", icon: "home" },
  { route: "harcamalar", label: "Harcamalar", icon: "list" },
  { route: "yeni", label: "Ekle", icon: "plus" },
  { route: "raporlar", label: "Raporlar", icon: "chart" },
  { route: "diger", label: "Menü", icon: "more" },
];

const MENU_ROUTES: readonly Route[] = [
  "diger",
  "gelirler",
  "sabit",
  "ayarlar",
  "kisiler",
  "hesaplar",
  "aktar",
  "kurallar",
  "takvim",
];

const TITLES: Record<Route, string> = {
  ozet: "Özet",
  harcamalar: "Harcamalar",
  yeni: "Yeni Harcama",
  gelirler: "Gelirler",
  raporlar: "Raporlar",
  sabit: "Sabit Giderler",
  ayarlar: "Ayarlar",
  kisiler: "Kişiler",
  bildirimler: "Bildirimler",
  hesaplar: "Hesaplar",
  aktar: "Ekstre",
  kurallar: "Kurallar",
  takvim: "Yaklaşanlar",
  diger: "Menü",
};

const DEFAULT_ROUTE: Route = "ozet";

export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [route, navigate, visit] = useHashRoute(DEFAULT_ROUTE);
  const [quickModalOpen, setQuickModalOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [me, bootstrap, users] = await Promise.all([api.me(), api.bootstrap(), api.users()]);
      setPhase({ kind: "ready", me, bootstrap, users });
    } catch (cause: unknown) {
      if (cause instanceof ApiError && cause.status === 401) {
        // Henuz yonetici yoksa giris ekrani yerine kurulum gosterilir.
        const setup = await api.setupStatus().catch(() => ({ required: false }));
        setPhase({ kind: setup.required ? "setup" : "login" });
      } else if (isNetworkError(cause)) {
        setPhase({ kind: "offline" });
      } else {
        setPhase({ kind: "failed", message: errorMessage(cause, "Bağlantı kurulamadı.") });
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onAuthRequired = () =>
      setPhase((current) => (current.kind === "ready" ? { kind: "login" } : current));
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  const retry = useCallback(() => {
    setPhase({ kind: "loading" });
    void load();
  }, [load]);

  const openQuickExpense = useCallback(() => {
    setQuickModalOpen(true);
  }, []);

  const session = useMemo<Session | null>(() => {
    if (phase.kind !== "ready") return null;
    return {
      me: phase.me,
      bootstrap: phase.bootstrap,
      users: phase.users,
      navigate,
      openQuickExpense,
      refresh: async () => {
        clearAsyncCache();
        const [bootstrap, users] = await Promise.all([api.bootstrap(), api.users()]);
        setPhase((current) => (current.kind === "ready" ? { ...current, bootstrap, users } : current));
      },
      setMe: (me: Me) =>
        setPhase((current) => (current.kind === "ready" ? { ...current, me } : current)),
      logout: async () => {
        clearAsyncCache();
        try {
          await api.logout();
        } catch {
          // Cerez zaten gecersizse de cikis yapilmis sayilir.
        }
        setPhase({ kind: "login" });
      },
    };
  }, [phase, navigate, openQuickExpense]);

  if (phase.kind === "loading") {
    return (
      <div className="center-screen">
        <Loading />
      </div>
    );
  }

  if (phase.kind === "offline") {
    return <OfflineScreen onRetry={retry} />;
  }

  if (phase.kind === "login") {
    return <Login onSuccess={retry} />;
  }

  if (phase.kind === "setup") {
    return <Setup onSuccess={retry} />;
  }

  if (phase.kind === "failed" || !session) {
    return (
      <div className="center-screen">
        <div className="empty">
          <span className="empty-icon">
            <Icon name="lock" size={22} />
          </span>
          <strong>Erişim sağlanamadı</strong>
          <span>{phase.kind === "failed" ? phase.message : ""}</span>
          <div className="empty-action">
            <button type="button" className="btn secondary" onClick={retry}>
              Tekrar dene
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <SessionContext.Provider value={session}>
      <ToastProvider>
        <Shell
          route={route}
          visit={visit}
          quickModalOpen={quickModalOpen}
          onCloseQuickModal={() => setQuickModalOpen(false)}
        />
      </ToastProvider>
    </SessionContext.Provider>
  );
}

/**
 * İnternet yokken açılış. Bütçe verisi gösterilemez (önbelleğe alınmaz), ama
 * hızlı giriş çalışır: kayıt bu cihazda bekler ve bağlantı gelince gönderilir.
 */
function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  const queue = useOfflineQueue();

  useEffect(() => {
    window.addEventListener("online", onRetry);
    return () => window.removeEventListener("online", onRetry);
  }, [onRetry]);

  return (
    <div className="offline-screen narrow stack">
      <div className="empty">
        <span className="empty-icon">
          <Icon name="wallet" size={22} />
        </span>
        <strong>İnternet bağlantısı yok</strong>
        <span>
          Harcamayı yine de yazabilirsiniz; bu cihazda bekler ve bağlantı gelince kaydedilir.
        </span>
        <div className="empty-action">
          <button type="button" className="btn secondary" onClick={onRetry}>
            Tekrar bağlan
          </button>
        </div>
      </div>
      <QuickEntry />
      <QueueList items={queue.items} />
    </div>
  );
}

/** Çevrimdışı kuyruk gönderilince haber verir; bekleyen varsa şerit gösterir. */
function OfflineQueueBanner({ route }: { route: Route }) {
  const { navigate } = useSession();
  const toast = useToast();
  const onSaved = useCallback(
    (count: number) => toast(`Çevrimdışı girilen ${count} harcama kaydedildi.`),
    [toast],
  );
  const { items } = useOfflineQueue(onSaved);
  if (items.length === 0 || route === "yeni") return null;
  const waiting = items.filter((item) => item.state !== "pending").length;
  return (
    <div className="alert info queue-banner" role="status">
      <span>
        {waiting > 0
          ? `Bu cihazda tamamlanması gereken ${waiting} harcama var.`
          : `Bu cihazda gönderilmeyi bekleyen ${items.length} harcama var.`}
      </span>
      <button type="button" className="btn ghost sm" onClick={() => navigate("yeni")}>
        Göster
      </button>
    </div>
  );
}

const UNREAD_POLL_MS = 60_000;

/** Okunmamış bildirim sayısı: dakikada bir, sekmeye dönünce ve değişince tazelenir. */
function useUnreadCount(route: Route): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api.notifications(0).then(
        (result) => {
          if (!cancelled) setCount(result.unread);
        },
        () => undefined,
      );
    void load();
    const timer = window.setInterval(load, UNREAD_POLL_MS);
    window.addEventListener("focus", load);
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", load);
      window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, load);
    };
  }, [route]);

  return count;
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

function Shell({
  route,
  visit,
  quickModalOpen,
  onCloseQuickModal,
}: {
  route: Route;
  visit: number;
  quickModalOpen: boolean;
  onCloseQuickModal: () => void;
}) {
  const { me, navigate, openQuickExpense, logout } = useSession();
  const toast = useToast();
  const initial = initialOf(me.display_name);
  const unread = useUnreadCount(route);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isEditableElement(event.target)) return;
      if (document.querySelector(".modal-backdrop")) return;

      if (event.key === "n" || event.key === "N") {
        event.preventDefault();
        openQuickExpense?.();
      } else if (event.key === "/") {
        event.preventDefault();
        if (route !== "harcamalar") {
          navigate("harcamalar");
          window.setTimeout(() => {
            document.getElementById("expense-search-input")?.focus();
          }, 60);
        } else {
          document.getElementById("expense-search-input")?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [route, navigate, openQuickExpense]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">İçeriğe geç</a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="wallet" size={20} />
          </span>
          <span>Aile Bütçesi<small className="brand-caption">Birlikte, daha dengeli.</small></span>
        </div>

        <button
          type="button"
          className="btn primary block"
          onClick={() => (openQuickExpense ? openQuickExpense() : navigate("yeni"))}
          title="Yeni harcama ekle (Kısayol: N)"
        >
          <Icon name="plus" size={18} />
          Harcama ekle
        </button>

        <nav className="nav" aria-label="Ana menü">
          {NAV_GROUPS.map((group) => {
            const visibleItems = group.items.filter((item) => !item.admin || me.is_admin);
            if (visibleItems.length === 0) return null;
            return (
              <div className="nav-group" key={group.title}>
                <div className="nav-group-title">{group.title}</div>
                {visibleItems.map((item) => (
                  <button
                    key={item.route}
                    type="button"
                    className={route === item.route ? "nav-link active" : "nav-link"}
                    aria-current={route === item.route ? "page" : undefined}
                    onClick={() => navigate(item.route)}
                  >
                    <Icon name={item.icon} />
                    {item.label}
                    {item.route === "bildirimler" && unread > 0 && (
                      <span className="badge danger" style={{ marginLeft: "auto" }}>
                        {unread}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <span className="avatar">{initial}</span>
          <span className="sidebar-user">
            <strong>{me.display_name}</strong>
            <span>{me.username ? `@${me.username}` : authSourceLabel(me.auth_source)}</span>
          </span>
          {me.auth_source === "session" && (
            <button
              type="button"
              className="icon-btn"
              onClick={() => void logout()}
              aria-label="Çıkış yap"
              title="Çıkış yap"
            >
              <Icon name="logout" size={18} />
            </button>
          )}
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <div className="brand mobile-only">
            <span className="brand-mark">
              <Icon name="wallet" size={18} />
            </span>
            {TITLES[route]}
          </div>
          <div className="topbar-hint desktop-only muted small">
            Kısayollar: <kbd>N</kbd> Yeni harcama · <kbd>/</kbd> Harcama ara
          </div>
          <div className="row topbar-actions">
            <ThemePicker compact />
            <button
              type="button"
              className="icon-btn"
              onClick={() => navigate("bildirimler")}
              aria-label={unread ? `Bildirimler, ${unread} okunmamış` : "Bildirimler"}
            >
              <Icon name="bell" size={20} />
              {unread > 0 && <span className="badge danger">{unread}</span>}
            </button>
            <button
              type="button"
              className="avatar avatar-btn"
              onClick={() => navigate("diger")}
              aria-label="Menü"
            >
              {initial}
            </button>
          </div>
        </header>

        <main className="main" id="main-content" tabIndex={-1}>
          {/* key={visit} burada değil sarmalayıcıda: her ziyarette taze bir
              DOM düğümü oluşur, bu yüzden app.css'teki giriş animasyonu her
              sayfa değişiminde yeniden oynar. */}
          <OfflineQueueBanner route={route} />
          <div className="page-enter" key={visit}>
            <Suspense fallback={<Loading />}>
              <Page route={route} />
            </Suspense>
          </div>
        </main>
      </div>

      <nav className="bottom-nav" aria-label="Alt menü">
        {MOBILE_NAV.map((item) => {
          const active =
            item.route === "diger" ? MENU_ROUTES.includes(route) : route === item.route;
          return (
            <button
              key={item.route}
              type="button"
              className={active ? "active" : undefined}
              aria-current={active ? "page" : undefined}
              onClick={() => navigate(item.route)}
            >
              {item.route === "yeni" ? (
                <span className="fab">
                  <Icon name="plus" size={24} />
                </span>
              ) : (
                <Icon name={item.icon} size={22} />
              )}
              {item.label}
            </button>
          );
        })}
      </nav>

      {quickModalOpen && (
        <Modal title="Harcama ekle" onClose={onCloseQuickModal} wide>
          <ExpenseForm
            submitLabel="Harcamayı kaydet"
            onCancel={onCloseQuickModal}
            onSubmit={async (input) => {
              const created = await api.createExpense(input);
              clearAsyncCache();
              toast(`${created.total.formatted} kaydedildi.`, "success", {
                label: "Geri al",
                run: async () => {
                  await api.deleteExpense(created.id);
                  clearAsyncCache();
                },
              });
              onCloseQuickModal();
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function Page({ route }: { route: Route }) {
  const { me } = useSession();
  switch (route) {
    case "ozet":
      return <Dashboard />;
    case "harcamalar":
      return <Expenses />;
    case "yeni":
      return <NewExpense />;
    case "gelirler":
      return <Incomes />;
    case "raporlar":
      return <Reports />;
    case "sabit":
      return <Recurring />;
    case "ayarlar":
      return <Settings />;
    case "kisiler":
      // Menude gizli olsa da adres elle yazilabilir ya da cikis yapan
      // yoneticiden kalmis olabilir; yonetici olmayan ozete duser.
      return me.is_admin ? <People /> : <Dashboard />;
    case "bildirimler":
      return <Notifications />;
    case "hesaplar":
      return <Accounts />;
    case "aktar":
      return <Statements />;
    case "kurallar":
      return <Rules />;
    case "takvim":
      return <Upcoming />;
    case "diger":
      return <More />;
  }
}
