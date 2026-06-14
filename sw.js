// JARVIS service worker — handles Web Push + notification taps
const VERSION = 'jarvis-v3';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Incoming push from your Hermes backend (via VAPID/pywebpush)
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {
    data = { title: 'J.A.R.V.I.S.', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'J.A.R.V.I.S.';
  const options = {
    body: data.body || '',
    icon: data.icon || './icons/icon-192.png',
    badge: './icons/icon-192.png',
    tag: data.tag || 'jarvis',
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

  // Body tap -> focus or open the app
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) { if ('focus' in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow(d.url || './index.html');
    })
  );
});
