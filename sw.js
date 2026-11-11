// Мережа спершу (свіжа база), кеш — коли немає інтернету. Так база доступна і офлайн.
const C = "skhemnyk-v2";
self.addEventListener("install", e => { e.waitUntil(caches.open(C).then(c => c.addAll(["./", "index.html", "manifest.json", "icon.svg", "icon-192.png", "sources.json"]))); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); } return r; })
    .catch(() => caches.match(e.request, {ignoreSearch: true}).then(r => r || caches.match("./"))));
});
