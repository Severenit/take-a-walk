/* Прогулки — service worker. Версия подставляется сборкой. */
const VERSION = '__VERSION__';
const SHELL = 'progulki-shell:' + VERSION;
const CORE = __CORE__;
const BASE = '__BASE__';

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(SHELL)
      .then((c) => c.addAll(CORE).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith('progulki-shell:') && k !== SHELL)
            .map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;

  // картинки — сначала из кэша, он же хранит сохранённые маршруты
  if (req.destination === 'image') {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).catch(() => new Response('', { status: 504 })))
    );
    return;
  }

  // страницы и ассеты — сеть, но с откатом в кэш, когда её нет
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match(BASE + '/')))
  );
});
