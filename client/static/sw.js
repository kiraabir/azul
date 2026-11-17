// AZUL Service Worker for PWA
const CACHE_NAME = 'azul-v1';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/azul.css',
  '/static/azul-logo.svg',
  '/manifest.json'
];

// Install event - cache assets
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch event - serve from cache, fall back to network
self.addEventListener('fetch', function(event) {
  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        if (response) {
          return response;
        }
        return fetch(event.request);
      }
  )});

// Push event - handle Web Push notifications
self.addEventListener('push', function(event) {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = { title: event.data.text() };
    }
  }

  const title = data.title || 'AZUL';
  const options = {
    body: data.body || 'New notification from AZUL',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/badge-72.png',
    data: {
      url: data.url || '/',
      ...data.data
    }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// Notification click - open app
self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});