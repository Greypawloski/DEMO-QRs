// Minimal service worker — network-only, no caching.
// Exists to satisfy PWA installability requirements without
// interfering with the dynamic Flask application.
self.addEventListener('fetch', function(event) {
  event.respondWith(fetch(event.request));
});
