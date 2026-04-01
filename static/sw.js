/* PWA: تمرير الطلبات للشبكة دون كاش قديم يتعارض مع /api */
self.addEventListener('install', (e) => {
  self.skipWaiting();
});
self.addEventListener('activate', (e) => {
  e.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', (e) => {
  e.respondWith(fetch(e.request));
});
