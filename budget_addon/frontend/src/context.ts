/**
 * Oturum bağlamı: giriş yapan kişi, başlangıç verisi ve gezinme.
 *
 * Sayfalar bu değerleri prop zinciriyle taşımak yerine buradan okur.
 */

import { createContext, useContext } from "react";

import type { AuthSource, Bootstrap, Me, UserSummary } from "./api";
import type { Route } from "./hooks";

export interface Session {
  me: Me;
  bootstrap: Bootstrap;
  users: UserSummary[];
  /** Kategori veya ödeme yöntemi değişince başlangıç verisini tazeler. */
  refresh: () => Promise<void>;
  setMe: (me: Me) => void;
  navigate: (route: Route) => void;
  logout: () => Promise<void>;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error("useSession yalnızca oturum açıkken kullanılabilir");
  }
  return session;
}

const SOURCE_LABELS: Record<AuthSource, string> = {
  session: "Web sitesi",
  ingress: "Home Assistant",
  telegram: "Telegram",
  dev: "Geliştirme",
};

export function authSourceLabel(source: AuthSource): string {
  return SOURCE_LABELS[source];
}

export function initialOf(name: string): string {
  return name.trim().charAt(0).toLocaleUpperCase("tr-TR") || "?";
}
