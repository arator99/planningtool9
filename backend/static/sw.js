/**
 * Planning Tool — Service Worker
 * Strategie:
 *   - Statische assets (CSS, JS, fonts): cache-first
 *   - Navigatieverzoeken (HTML): network-first, fallback naar /offline
 *   - API-verzoeken: network-only (nooit cachen)
 */

const CACHE_NAAM = 'planningtool-v0.9.0';
const OFFLINE_URL = '/offline';

// Bestanden die bij installatie worden gecached
const PRECACHE = [
  '/static/css/output.css',
  '/offline',
];

// ── Installatie: precache assets ──────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAAM).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

// ── Activering: verwijder oude caches ─────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((namen) =>
      Promise.all(
        namen
          .filter((naam) => naam !== CACHE_NAAM)
          .map((naam) => caches.delete(naam))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: routingstrategie ───────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API-verzoeken altijd via het netwerk (nooit cachen)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/health')) {
    return;
  }

  // Statische assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const kopie = response.clone();
            caches.open(CACHE_NAAM).then((cache) => cache.put(request, kopie));
          }
          return response;
        });
      })
    );
    return;
  }

  // Navigatieverzoeken: network-first, fallback naar /offline
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE_URL).then((cached) => cached || new Response('Offline', { status: 503 }))
      )
    );
    return;
  }
});
