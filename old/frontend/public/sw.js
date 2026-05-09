// Placeholder service worker to avoid 404 on /sw.js from stale localhost registrations.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
