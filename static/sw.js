/**
 * Beacon service worker.
 *
 * Deliberately conservative about what it caches, because this is a
 * financial app: showing someone a stale wallet balance or a stale
 * "claimed" status from cache would be a real correctness bug, not just
 * a UX one. So the rule is simple —
 *
 *   - Static assets (CSS, JS, icons, fonts) under /static/  → cache-first.
 *     These are versioned by CACHE_NAME below and rarely change, so
 *     caching them aggressively is safe and makes repeat loads instant.
 *
 *   - Everything else (every actual page — dashboard, wallet, buy,
 *     links, claim pages, etc.) → ALWAYS network. Never served from
 *     cache, never written to cache. If the network fails, the person
 *     sees the offline fallback page instead of stale data.
 *
 * Bump CACHE_NAME whenever static assets change, so old cached files
 * get cleaned up on the next activate.
 */

const CACHE_NAME = 'beacon-static-v1';
const OFFLINE_URL = '/static/offline.html';

const PRECACHE_URLS = [
  OFFLINE_URL,
  '/static/css/style.css',
  '/static/css/auth.css',
  '/static/css/links.css',
  '/static/css/pin_pad.css',
  '/static/css/transactions.css',
  '/static/css/settings.css',
  '/static/css/wallet.css',
  '/static/js_/pin_pad.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // Cache the offline fallback on its own, with its own error
      // handling — this one is load-bearing for the entire offline
      // feature, so it shouldn't be able to silently fail just because
      // some unrelated asset in PRECACHE_URLS 404s (cache.addAll() is
      // all-or-nothing: ONE bad URL fails the WHOLE install, and nothing
      // gets cached at all — including this file).
      try {
        await cache.add(OFFLINE_URL);
      } catch (err) {
        console.error('Beacon SW: failed to precache offline fallback — offline mode will not work:', err);
      }

      // Best-effort for everything else. A single renamed/missing asset
      // (e.g. a hashed filename from collectstatic that drifted out of
      // sync with this list) shouldn't be able to take down install.
      await Promise.all(
        PRECACHE_URLS.filter((url) => url !== OFFLINE_URL).map((url) =>
          cache.add(url).catch((err) => console.warn('Beacon SW: could not precache', url, err))
        )
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Only ever intercept GET — never touch POST (form submits, PIN
  // confirmation, claim-link redemption, etc.). Anything else falls
  // through to the browser's normal network handling untouched.
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  const isStaticAsset = url.pathname.startsWith('/static/');

  if (isStaticAsset) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Real pages: network-only, with an offline fallback if the network
  // is unreachable. Nothing here ever gets written to cache.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL))
    );
  }
  // Non-navigation, non-static GETs (e.g. an API call) are left alone —
  // no event.respondWith means the browser handles it normally.
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
  }
  return response;
}
