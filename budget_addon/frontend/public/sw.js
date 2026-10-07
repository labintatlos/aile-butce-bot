/*
 * Servis çalışanı: anlık bildirimler ve çevrimdışı açılış.
 *
 * Bütçe verisi (`api/...`) hiçbir zaman önbelleğe alınmaz; eski bir kopyayı
 * güncelmiş gibi göstermek yanıltıcı olurdu. Önbelleğe yalnızca uygulamanın
 * kabuğu (sayfa, betik, stil, simge) alınır ve o da **önce ağ** kuralıyla:
 * bağlantı varken her şey sunucudan taze gelir, önbellek yalnızca bağlantı
 * yokken devreye girer. Böylece markette, otoparkta internet yokken de site
 * açılır ve harcama kuyruğa yazılabilir.
 */

const SHELL_CACHE = "butce-kabuk-v1";

/*
 * Kurulumda sayfa ve onun yüklediği derlenmiş betik/stil dosyaları hemen
 * önbelleğe alınır. Yoksa ilk ziyaretten hemen sonra bağlantı giderse site
 * açılmazdı. Başarısız olursa kurulum yine tamamlanır; önbellek ilk gezintide
 * dolar.
 */
async function precacheShell() {
  const cache = await caches.open(SHELL_CACHE);
  const scope = self.registration.scope;
  const response = await fetch(scope, { cache: "no-store" });
  if (!response.ok) return;
  const html = await response.clone().text();
  await cache.put(scope, response);
  const assets = new Set(["manifest.json", "icon-192.png"]);
  for (const match of html.matchAll(/(?:src|href)="(?:\.\/)?(assets\/[^"]+)"/g)) {
    assets.add(match[1]);
  }
  const wanted = new Set([...assets].map((path) => new URL(path, scope).href));
  await Promise.all([...wanted].map((url) => cache.add(url).catch(() => undefined)));
  // Önceki sürümlerin adı karma içeren dosyaları artık kullanılmaz; birikmesin.
  for (const request of await cache.keys()) {
    if (request.url.includes("/assets/") && !wanted.has(request.url)) await cache.delete(request);
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(precacheShell().catch(() => undefined).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) =>
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((name) => name.startsWith("butce-") && name !== SHELL_CACHE)
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  ),
);

function isShellRequest(request) {
  if (request.method !== "GET") return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  const scope = new URL(self.registration.scope);
  if (!url.pathname.startsWith(scope.pathname)) return false;
  const path = url.pathname.slice(scope.pathname.length);
  return !path.startsWith("api/");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (!isShellRequest(request)) return;
  event.respondWith(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      try {
        const response = await fetch(request);
        if (response.ok && response.type === "basic") {
          // Sayfa adresinin sorgu ve parçası farklı olabilir; tek kopya tutulur.
          const key = request.mode === "navigate" ? self.registration.scope : request;
          await cache.put(key, response.clone());
        }
        return response;
      } catch (error) {
        const cached =
          (await cache.match(request, { ignoreSearch: true })) ||
          (request.mode === "navigate" ? await cache.match(self.registration.scope) : undefined);
        if (cached) return cached;
        throw error;
      }
    })(),
  );
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Aile Bütçesi", {
      body: data.body || "",
      icon: "icon-192.png",
      badge: "icon-192.png",
      tag: data.tag,
      data: { url: data.url || "#/bildirimler" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "#/bildirimler", self.registration.scope).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of windows) {
        if (client.url.startsWith(self.registration.scope)) {
          if ("navigate" in client) await client.navigate(target).catch(() => undefined);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    })(),
  );
});
