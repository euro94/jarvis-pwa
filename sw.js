// AETHER service worker — Web Push + notification taps + offline app shell
const VERSION = 'aether-v83';
const SHELL = 'aether-shell-' + VERSION;

// The static shell. Cached on install so the app opens (and shows a real
// offline state) with no network instead of a white screen. Dynamic data
// (ntfy polls/pushes) is intentionally NOT cached — it must always hit network.
const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/maskable-192.png',
  './icons/maskable-512.png',
  './icons/mark-256.png',
  './assets/aether-logo.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(SHELL_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('aether-shell-') && k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Serve the app shell offline. Only same-origin GET navigations + precached
// assets are handled here; everything else (ntfy on the tailnet, uploads, the
// Nous portal) falls through to the network untouched so live data is never
// served stale.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;

  // Navigations: network-first (fresh app), fall back to cached shell offline.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('./index.html').then((r) => r || caches.match('./')))
    );
    return;
  }

  // Precached static assets: cache-first.
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).catch(() => cached))
  );
});

// Incoming push from your Hermes backend (via VAPID/pywebpush)
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {
    data = { title: 'AETHER', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'AETHER';
  const options = {
    body: data.body || '',
    icon: data.icon || './icons/icon-192.png',
    badge: './icons/icon-192.png',
    tag: data.tag || ('aether-' + Date.now()),
    renotify: true,
    requireInteraction: !!data.requireInteraction,
    data: { url: data.url || './index.html', actionUrls: data.actionUrls || {}, actionBodies: data.actionBodies || {} },
    actions: data.actions || []
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// Tap on notification or an action button -> silently ping backend and/or open app
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const d = event.notification.data || {};
  const action = event.action;

  // Action buttons fire a fire-and-forget POST (one-tap habit logging, no app open)
  if (action && d.actionUrls && d.actionUrls[action]) {
    const opts = { method: 'POST', mode: 'no-cors', keepalive: true };
    if (d.actionBodies && d.actionBodies[action]) opts.body = d.actionBodies[action];
    event.waitUntil(fetch(d.actionUrls[action], opts).catch(() => {}));
    return;
  }

  // Body tap -> open app AT the target url, or if already open, navigate/notify it
  const target = d.url || './index.html';
  // extract ?log=<habit> so we can tell an already-open page to show the sheet
  let logHabit = null;
  try { logHabit = new URL(target, self.location.href).searchParams.get('log'); } catch (e) {}

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        // Tell the already-open page to show the log sheet immediately
        if (logHabit && 'postMessage' in c) c.postMessage({ type: 'show-log', habit: logHabit });
        if ('navigate' in c) { try { c.navigate(target); } catch (e) {} }
        if ('focus' in c) return c.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
    })
  );
});
