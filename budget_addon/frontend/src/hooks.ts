/**
 * Ortak React kancaları: adres çubuğundaki sayfa ve sunucudan veri yükleme.
 *
 * Yönlendirme `#/sayfa` biçimindedir. Home Assistant Ingress uygulamayı bir yol
 * önekinin altında sunar; yolu değiştiren bir yönlendirici orada 404 üretirdi,
 * karma (hash) ise önekten bağımsızdır.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

export type Route =
  | "ozet"
  | "harcamalar"
  | "yeni"
  | "gelirler"
  | "raporlar"
  | "sabit"
  | "ayarlar"
  | "kisiler"
  | "bildirimler"
  | "hesaplar"
  | "aktar"
  | "kurallar"
  | "takvim"
  | "diger";

export function isRoute(name: string): name is Route {
  return (ROUTES as readonly string[]).includes(name);
}

const ROUTES: readonly Route[] = [
  "ozet",
  "harcamalar",
  "yeni",
  "gelirler",
  "raporlar",
  "sabit",
  "ayarlar",
  "kisiler",
  "bildirimler",
  "hesaplar",
  "aktar",
  "kurallar",
  "takvim",
  "diger",
];

function readHash(fallback: Route): Route {
  const name = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : fallback;
}

/**
 * Etkin sayfa, gezinme işlevi ve ziyaret sayacı.
 *
 * Sayaç her gezinmede artar. Sayfa bu sayaçla anahtarlandığında, zaten açık
 * olan sayfaya yeniden basmak onu sıfırlar: kayıt özetindeyken "Ekle"ye basan
 * kişi boş forma döner.
 */
export function useHashRoute(fallback: Route): [Route, (route: Route) => void, number] {
  const [route, setRoute] = useState<Route>(() => readHash(fallback));
  const [visit, setVisit] = useState(0);

  useEffect(() => {
    const onChange = () => setRoute(readHash(fallback));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, [fallback]);

  const navigate = useCallback(
    (next: Route) => {
      if (readHash(fallback) === next) {
        setRoute(next);
      } else {
        window.location.hash = `/${next}`;
      }
      setVisit((value) => value + 1);
      window.scrollTo({ top: 0 });
    },
    [fallback],
  );

  return [route, navigate, visit];
}

export function errorMessage(
  cause: unknown,
  fallback = "İşlem tamamlanamadı. Lütfen tekrar deneyin.",
): string {
  return cause instanceof ApiError ? cause.message : fallback;
}

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

const ASYNC_CACHE = new Map<string, unknown>();

/** Tüm bellek içi veri önbelleğini temizler (ör. çıkış yapıldığında veya kayıt değiştiğinde). */
export function clearAsyncCache(prefix?: string): void {
  if (!prefix) {
    ASYNC_CACHE.clear();
    return;
  }
  for (const key of ASYNC_CACHE.keys()) {
    if (key.startsWith(prefix)) ASYNC_CACHE.delete(key);
  }
}

/**
 * Veriyi yükler; bağımlılıklar değişince yeniden yükler.
 *
 * `cacheKey` verilirse sayfa geçişlerinde son bilinen veri anında gösterilir
 * ve arka planda sessizce tazelenir (stale-while-revalidate).
 */
export function useAsync<T>(
  load: () => Promise<T>,
  deps: readonly unknown[],
  cacheKey?: string,
): AsyncState<T> {
  const fullKey = cacheKey ? `${cacheKey}:${JSON.stringify(deps)}` : undefined;
  const [data, setData] = useState<T | null>(() =>
    fullKey && ASYNC_CACHE.has(fullKey) ? (ASYNC_CACHE.get(fullKey) as T) : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(() => !(fullKey && ASYNC_CACHE.has(fullKey)));
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let cancelled = false;
    if (fullKey && ASYNC_CACHE.has(fullKey)) {
      setData(ASYNC_CACHE.get(fullKey) as T);
    }
    setLoading(true);
    setError(null);
    loadRef.current().then(
      (value) => {
        if (cancelled) return;
        if (fullKey) ASYNC_CACHE.set(fullKey, value);
        setData(value);
        setLoading(false);
      },
      (cause: unknown) => {
        if (cancelled) return;
        setError(errorMessage(cause, "Veriler yüklenemedi."));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, fullKey]);

  const reload = useCallback(() => {
    if (fullKey) ASYNC_CACHE.delete(fullKey);
    setTick((value) => value + 1);
  }, [fullKey]);
  return { data, error, loading, reload };
}
