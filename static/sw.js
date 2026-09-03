const CACHE = "somled-v5";
const CORE = [
  "/static/manifest.webmanifest?v=6",
  "/static/icon-192.png?v=6",
  "/static/icon-512.png?v=6",
  "/static/apple-touch-icon.png?v=6",
  "/static/favicon-32.png?v=6",
  "/static/favicon-16.png?v=6",
  "/static/estilo.css?v=6",
  "/static/utilitarios.js?v=6",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname === "/login" || url.pathname === "/logout") return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request)
        .then((response) => {
          if (response && response.ok) {
            const clone = response.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
