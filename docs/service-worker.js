const CACHE_VERSION = 'kucharka-v1';
const APP_CACHE = `kucharka-app-${CACHE_VERSION}`;
const DATA_CACHE = `kucharka-data-${CACHE_VERSION}`;
const APP_SHELL = [
  './',
  './index.html',
  './styles.css',
  './app.js',
  './manifest.webmanifest'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(APP_CACHE).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => key.startsWith('kucharka-') && key !== APP_CACHE && key !== DATA_CACHE)
        .map((key) => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

function isDataRequest(request) {
  const url = new URL(request.url);
  return url.pathname.endsWith('/recepty.json') || url.pathname.includes('/obrazky/');
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(DATA_CACHE);
      cache.put(request, response.clone());
      return response;
    }
    throw new Error('Network unavailable');
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    return Response.error();
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }

  const response = await fetch(request);
  if (response && response.ok) {
    const cache = await caches.open(APP_CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(APP_CACHE).then((cache) => cache.put('./index.html', copy));
        return response;
      }).catch(() => caches.match('./index.html'))
    );
    return;
  }

  if (isDataRequest(request)) {
    event.respondWith(networkFirst(request));
    return;
  }

  event.respondWith(cacheFirst(request));
});
