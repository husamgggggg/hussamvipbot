/* Abood Trader — كاش للأصول الثابتة فقط؛ /api والصفحات دائماً من الشبكة */
const CACHE = 'abood-static-v2';
const PRECACHE = [
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/screenshot-wide.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) {
    event.respondWith(fetch(req));
    return;
  }
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(req));
    return;
  }
  if (req.method !== 'GET') {
    event.respondWith(fetch(req));
    return;
  }
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(fetch(req));
    return;
  }

  const path = url.pathname;
  const useCache = PRECACHE.includes(path);
  if (!useCache) {
    event.respondWith(fetch(req));
    return;
  }

  event.respondWith(
    caches.match(req).then((hit) => {
      if (hit) {
        fetch(req)
          .then((res) => {
            if (res && res.ok)
              caches.open(CACHE).then((c) => c.put(req, res.clone()));
          })
          .catch(() => {});
        return hit;
      }
      return fetch(req).then((res) => {
        if (res && res.ok)
          caches.open(CACHE).then((c) => c.put(req, res.clone()));
        return res;
      });
    })
  );
});
