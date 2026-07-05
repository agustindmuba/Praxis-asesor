// Service Worker mínimo para PWA de Praxis Asesor.
//
// Objetivo v1: hacer la app INSTALABLE (requisito de Chrome / Edge / Android
// para el prompt "Añadir a pantalla de inicio"). No hace caching agresivo:
// las páginas son casi todas dinámicas y auth-gated, cachearlas rompería
// más de lo que ayuda. Un fetch handler mínimo alcanza para instalabilidad.
//
// Bumpear CACHE_VERSION cuando cambien assets del shell (íconos, manifest).
const CACHE_VERSION = 'praxis-v1';
const SHELL = [
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_VERSION)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Sólo GET, mismo origen. POST / cross-origin al red directo.
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Assets del shell → cache-first. Todo lo demás → network con fallback
  // silencioso al cache si estamos offline y ya lo vimos antes.
  event.respondWith(
    (async () => {
      const cached = await caches.match(req);
      try {
        const fresh = await fetch(req);
        // Sólo guardamos assets estáticos, no HTML dinámico ni /api/.
        if (
          fresh.ok &&
          (url.pathname.startsWith('/_next/static/') ||
            url.pathname.startsWith('/icon-') ||
            url.pathname === '/manifest.webmanifest' ||
            url.pathname === '/apple-touch-icon.png')
        ) {
          const clone = fresh.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(req, clone));
        }
        return fresh;
      } catch (_err) {
        // Offline. Devolvemos lo cacheado si lo hay.
        return cached || Response.error();
      }
    })()
  );
});
