/* Shaggoth service worker.
 *
 * The previous version was cache-first over every same-origin request, with a
 * cache name that never changed and no cleanup on activate. Two consequences,
 * both bad:
 *
 *   1. Anyone who had ever loaded the site was pinned to that first copy of
 *      index.html / app.js forever. Deploys could not reach them at all --
 *      including anyone reporting a bug that had already been fixed.
 *   2. Shaggoth's API lives at the root (/chat, /curiosity/status, /knowledge),
 *      not under /api/, so GET endpoints were being served from cache too. The
 *      dashboard could show yesterday's knowledge count while the daemon was
 *      running fine.
 *
 * Strategy now, by request kind:
 *
 *   API + navigations -> network first, cache only as an offline fallback.
 *     Correctness beats speed here; a stale answer is worse than a slow one.
 *   Versioned assets (?v=) -> cache first. The URL changes when the file
 *     does, so a hit is always current.
 *   Everything else same-origin -> stale-while-revalidate.
 *
 * Bump CACHE_VERSION when this file's logic changes.
 */

const CACHE_VERSION = 'v3';
const CACHE = `shaggoth-${CACHE_VERSION}`;

// Only the entry points. Hashed assets arrive on demand and are cached by URL.
const PRECACHE = ['/', '/manifest.json', '/favicon.svg'];

// Shaggoth's API is at the root, so it is matched by prefix rather than by a
// single /api/ namespace.
const API_PREFIXES = [
  '/chat', '/health', '/history', '/facts', '/guardrails', '/learn',
  '/scrape', '/curiosity', '/knowledge', '/personality', '/wiki', '/greeting',
];

const isApi = (path) => API_PREFIXES.some((p) => path === p || path.startsWith(p + '/'));

const offlineJson = () =>
  new Response(JSON.stringify({ error: 'offline', reply: "Can't reach the server." }), {
    status: 503,
    headers: { 'Content-Type': 'application/json' },
  });

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Drop every cache from a previous version. Without this the old entries
  // survive forever and keep being served.
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(names.filter((n) => n !== CACHE).map((n) => caches.delete(n)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Never touch non-GET (chat is a POST) or cross-origin requests.
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (isApi(url.pathname)) {
    event.respondWith(fetch(request).catch(offlineJson));
    return;
  }

  // Navigations: always try the network so a deploy lands immediately.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
          return response;
        })
        .catch(() => caches.match(request).then((r) => r || caches.match('/')))
    );
    return;
  }

  // Versioned assets are safe to serve from cache: the URL carries the version.
  const versioned = url.searchParams.has('v');

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached && versioned) return cached;

      const network = fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => cached);

      // Stale-while-revalidate: answer now, refresh for next time.
      return cached || network;
    })
  );
});


/* ---------------------------------------------------------------- push
 *
 * Shaggoth researches on a timer whether anyone is watching, and answers
 * questions long after they were asked. These handlers are how it says so.
 */

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    // A push with a non-JSON body is still worth showing.
    payload = { body: event.data ? event.data.text() : '' };
  }

  const title = payload.title || 'Shaggoth';
  const options = {
    body: payload.body || '',
    icon: '/pwa-192.png',
    badge: '/pwa-192.png',
    // Same tag replaces rather than stacks, so a quiet night does not leave
    // a wall of identical notifications.
    tag: payload.tag || 'shaggoth',
    renotify: false,
    data: { url: payload.url || '/' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';

  // Focus an existing tab rather than piling up new ones.
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((windows) => {
        for (const client of windows) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            client.navigate(target).catch(() => {});
            return client.focus();
          }
        }
        return self.clients.openWindow(target);
      })
  );
});
