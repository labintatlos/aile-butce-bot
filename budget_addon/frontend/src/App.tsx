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

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  AUTH_REQUIRED_EVENT,
  NOTIFICATIONS_CHANGED_EVENT,
  type Bootstrap,
  type Me,
  type UserSummary,
} from "./api";
import { Icon, type IconName } from "./components/icons";
import { Loading, ToastProvider } from "./components/ui";
import { authSourceLabel, initialOf, SessionContext, useSession, type Session } from "./context";
import { errorMessage, useHashRoute, type Route } from "./hooks";
import { Dashboard } from "./pages/Dashboard";
import { Expenses } from "./pages/Expenses";
import { Incomes } from "./pages/Incomes";
import { Login } from "./pages/Login";
import { More } from "./pages/More";
import { NewExpense } from "./pages/NewExpense";
import { Notifications } from "./pages/Notifications";
import { People } from "./pages/People";
import { Recurring } from "./pages/Recurring";
import { Reports } from "./pages/Reports";
import { Settings } from "./pages/Settings";
import { Setup } from "./pages/Setup";

type Phase =
  | { kind: "loading" }
  | { kind: "login" }
  | { kind: "setup" }
  | { kind: "failed"; message: string }
  | { kind: "ready"; me: Me; bootstrap: Bootstrap; users: UserSummary[] };

const NAV: readonly { route: Route; label: string; icon: IconName; admin?: boolean }[] = [
  { route: "ozet", label: "Özet", icon: "home" },
  { route: "harcamalar", label: "Harcamalar", icon: "list" },
  { route: "gelirler", label: "Gelirler", icon: "income" },
  { route: "raporlar", label: "Raporlar", icon: "chart" },
  { route: "sabit", label: "Sabit Giderler", icon: "repeat" },
  { route: "bildirimler", label: "Bildirimler", icon: "bell" },
  { route: "ayarlar", label: "Ayarlar", icon: "settings" },
  { route: "kisiler", label: "Kişiler", icon: "users", admin: true },
];

const MOBILE_NAV: readonly { route: Route; label: string; icon: IconName }[] = [
  { route: "ozet", label: "Özet", icon: "home" },
  { route: "harcamalar", label: "Harcamalar", icon: "list" },
  { route: "yeni", label: "Ekle", icon: "plus" },
  { route: "raporlar", label: "Raporlar", icon: "chart" },
  { route: "diger", label: "Menü", icon: "more" },
];

const MENU_ROUTES: readonly Route[] = ["diger", "gelirler", "sabit", "ayarlar", "kisiler"];

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
  diger: "Menü",
};

const DEFAULT_ROUTE: Route = "ozet";

export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [route, navigate, visit] = useHashRoute(DEFAULT_ROUTE);

  const load = useCallback(async () => {
    try {
      const [me, bootstrap, users] = await Promise.all([api.me(), api.bootstrap(), api.users()]);
      setPhase({ kind: "ready", me, bootstrap, users });
    } catch (cause: unknown) {
      if (cause instanceof ApiError && cause.status === 401) {
        // Henuz yonetici yoksa giris ekrani yerine kurulum gosterilir.
        const setup = await api.setupStatus().catch(() => ({ required: false }));
        setPhase({ kind: setup.required ? "setup" : "login" });
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

  const session = useMemo<Session | null>(() => {
    if (phase.kind !== "ready") return null;
    return {
      me: phase.me,
      bootstrap: phase.bootstrap,
      users: phase.users,
      navigate,
      refresh: async () => {
        const [bootstrap, users] = await Promise.all([api.bootstrap(), api.users()]);
        setPhase((current) => (current.kind === "ready" ? { ...current, bootstrap, users } : current));
      },
      setMe: (me: Me) =>
        setPhase((current) => (current.kind === "ready" ? { ...current, me } : current)),
      logout: async () => {
        try {
          await api.logout();
        } catch {
          // Cerez zaten gecersizse de cikis yapilmis sayilir.
        }
        setPhase({ kind: "login" });
      },
    };
  }, [phase, navigate]);

  if (phase.kind === "loading") {
    return (
      <div className="center-screen">
        <Loading />
      </div>
    );
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
        <Shell route={route} visit={visit} />
      </ToastProvider>
    </SessionContext.Provider>
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

function Shell({ route, visit }: { route: Route; visit: number }) {
  const { me, navigate, logout } = useSession();
  const initial = initialOf(me.display_name);
  const unread = useUnreadCount(route);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="wallet" size={20} />
          </span>
          Aile Bütçe
        </div>

        <button type="button" className="btn primary block" onClick={() => navigate("yeni")}>
          <Icon name="plus" size={18} />
          Harcama ekle
        </button>

        <nav className="nav" aria-label="Ana menü">
          {NAV.filter((item) => !item.admin || me.is_admin).map((item) => (
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
          <div className="brand">
            <span className="brand-mark">
              <Icon name="wallet" size={18} />
            </span>
            {TITLES[route]}
          </div>
          <div className="row">
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

        <main className="main">
          <Page key={visit} route={route} />
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
    case "diger":
      return <More />;
  }
}
