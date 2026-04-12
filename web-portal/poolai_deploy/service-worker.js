/**
 * PoolAIssistant Service Worker v2
 * Provides offline support, caching, and PWA functionality
 */

const CACHE_VERSION = 'poolai-v2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const API_CACHE = `${CACHE_VERSION}-api`;
const IMAGE_CACHE = `${CACHE_VERSION}-images`;

// Static assets to precache on install
const STATIC_ASSETS = [
  '/',
  '/dashboard.php',
  '/login.php',
  '/install.php',
  '/offline.php',
  '/account.php',
  '/assets/css/portal.css',
  '/assets/js/pwa.js',
  '/manifest.json'
];

// API endpoints that should be cached
const CACHEABLE_API_PATTERNS = [
  /\/api\/devices?\/?$/,
  /\/api\/device\/\d+\/status$/,
  /\/api\/device\/\d+\/readings$/,
  /\/api\/device\/\d+\/health$/
];

// Max age for cached content (in milliseconds)
const CACHE_MAX_AGE = {
  api: 5 * 60 * 1000,      // 5 minutes for API
  dynamic: 24 * 60 * 60 * 1000, // 24 hours for pages
  static: 7 * 24 * 60 * 60 * 1000 // 7 days for static assets
};

// Install event - precache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker v2...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Precaching static assets');
        const requests = STATIC_ASSETS.map(url =>
          new Request(url, { credentials: 'same-origin' })
        );
        return Promise.allSettled(
          requests.map(req =>
            cache.add(req).catch(err => {
              console.log(`[SW] Failed to cache: ${req.url}`, err.message);
            })
          )
        );
      })
      .then(() => {
        console.log('[SW] Static assets cached');
        return self.skipWaiting();
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  event.waitUntil(
    caches.keys()
      .then((keys) => {
        return Promise.all(
          keys
            .filter(key => key.startsWith('poolai-') && !key.startsWith(CACHE_VERSION))
            .map(key => {
              console.log('[SW] Removing old cache:', key);
              return caches.delete(key);
            })
        );
      })
      .then(() => {
        console.log('[SW] Claiming clients');
        return self.clients.claim();
      })
      .then(() => {
        // Notify all clients about the update
        return self.clients.matchAll().then(clients => {
          clients.forEach(client => {
            client.postMessage({ type: 'SW_UPDATED', version: CACHE_VERSION });
          });
        });
      })
  );
});

// Fetch event - smart caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip cross-origin requests (except CDN assets)
  if (url.origin !== location.origin && !isTrustedCDN(url)) return;

  // Skip chrome-extension and other special protocols
  if (!url.protocol.startsWith('http')) return;

  // Handle different request types
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(handleApiRequest(request));
  } else if (isStaticAsset(url.pathname)) {
    event.respondWith(handleStaticAsset(request));
  } else if (isImageAsset(url.pathname)) {
    event.respondWith(handleImageAsset(request));
  } else {
    event.respondWith(handlePageRequest(request));
  }
});

// API requests: Network first, cache fallback
async function handleApiRequest(request) {
  const url = new URL(request.url);

  // Check if this API endpoint should be cached
  const shouldCache = CACHEABLE_API_PATTERNS.some(pattern => pattern.test(url.pathname));

  try {
    const response = await fetch(request);

    if (response.ok && shouldCache) {
      const cache = await caches.open(API_CACHE);
      const responseToCache = response.clone();

      // Add timestamp header for cache validation
      const headers = new Headers(responseToCache.headers);
      headers.set('X-Cache-Time', Date.now().toString());

      cache.put(request, new Response(await responseToCache.blob(), {
        status: responseToCache.status,
        statusText: responseToCache.statusText,
        headers
      }));
    }

    return response;
  } catch (error) {
    console.log('[SW] API fetch failed, checking cache:', url.pathname);

    const cached = await caches.match(request);
    if (cached) {
      const cacheTime = parseInt(cached.headers.get('X-Cache-Time') || '0');
      const age = Date.now() - cacheTime;

      // Return cached response with staleness indicator
      const headers = new Headers(cached.headers);
      headers.set('X-From-Cache', 'true');
      headers.set('X-Cache-Age', Math.round(age / 1000).toString());

      return new Response(cached.body, {
        status: cached.status,
        statusText: cached.statusText,
        headers
      });
    }

    return new Response(JSON.stringify({
      error: 'offline',
      message: 'No cached data available'
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// Static assets: Cache first, network fallback
async function handleStaticAsset(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.log('[SW] Static asset fetch failed:', request.url);
    return new Response('', { status: 503 });
  }
}

// Image assets: Cache first with lazy caching
async function handleImageAsset(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(IMAGE_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // Return a placeholder or empty response for images
    return new Response('', {
      status: 503,
      headers: { 'Content-Type': 'image/svg+xml' }
    });
  }
}

// Page requests: Network first, cache fallback, offline page
async function handlePageRequest(request) {
  try {
    const response = await fetch(request);

    if (response.ok && response.type === 'basic') {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }

    return response;
  } catch (error) {
    console.log('[SW] Page fetch failed, checking cache:', request.url);

    // Try cached version
    const cached = await caches.match(request);
    if (cached) return cached;

    // Try offline page
    const offlinePage = await caches.match('/offline.php');
    if (offlinePage) return offlinePage;

    // Last resort
    return new Response(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Offline - PoolAIssistant</title>
        <style>
          body { font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f8fafc; color: #334155; text-align: center; padding: 20px; }
          .container { max-width: 400px; }
          h1 { color: #0f172a; margin-bottom: 0.5rem; }
          p { color: #64748b; }
          button { background: #0066cc; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer; margin-top: 20px; }
          button:hover { background: #0052a3; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>You're Offline</h1>
          <p>Please check your internet connection and try again.</p>
          <button onclick="location.reload()">Retry</button>
        </div>
      </body>
      </html>
    `, {
      status: 503,
      headers: { 'Content-Type': 'text/html' }
    });
  }
}

// Helper: Check if URL is a static asset
function isStaticAsset(pathname) {
  return /\.(css|js|woff|woff2|ttf|eot|json)$/i.test(pathname);
}

// Helper: Check if URL is an image
function isImageAsset(pathname) {
  return /\.(png|jpg|jpeg|gif|svg|ico|webp)$/i.test(pathname);
}

// Helper: Check if URL is from a trusted CDN
function isTrustedCDN(url) {
  const trustedHosts = [
    'cdn.plot.ly',
    'fonts.googleapis.com',
    'fonts.gstatic.com'
  ];
  return trustedHosts.some(host => url.hostname.includes(host));
}

// Handle messages from main thread
self.addEventListener('message', (event) => {
  const { type, data } = event.data || {};

  switch (type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;

    case 'CLEAR_CACHE':
      event.waitUntil(
        caches.keys().then(keys =>
          Promise.all(keys.map(key => caches.delete(key)))
        ).then(() => {
          event.ports[0]?.postMessage({ success: true });
        })
      );
      break;

    case 'CACHE_URLS':
      if (data?.urls) {
        event.waitUntil(
          caches.open(DYNAMIC_CACHE).then(cache =>
            Promise.allSettled(data.urls.map(url => cache.add(url)))
          )
        );
      }
      break;

    case 'GET_CACHE_SIZE':
      event.waitUntil(
        getCacheSize().then(size => {
          event.ports[0]?.postMessage({ size });
        })
      );
      break;
  }
});

// Get total cache size
async function getCacheSize() {
  const cacheNames = await caches.keys();
  let totalSize = 0;

  for (const name of cacheNames) {
    const cache = await caches.open(name);
    const keys = await cache.keys();

    for (const request of keys) {
      const response = await cache.match(request);
      if (response) {
        const blob = await response.clone().blob();
        totalSize += blob.size;
      }
    }
  }

  return totalSize;
}

// Background sync for offline actions
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync triggered:', event.tag);

  switch (event.tag) {
    case 'sync-device-data':
      event.waitUntil(syncDeviceData());
      break;
    case 'sync-pending-actions':
      event.waitUntil(syncPendingActions());
      break;
  }
});

async function syncDeviceData() {
  console.log('[SW] Syncing device data...');
  // Implement background data sync
}

async function syncPendingActions() {
  console.log('[SW] Syncing pending actions...');
  // Implement pending action sync
}

// Push notifications
self.addEventListener('push', (event) => {
  if (!event.data) return;

  let data;
  try {
    data = event.data.json();
  } catch {
    data = { title: 'PoolAIssistant', body: event.data.text() };
  }

  const options = {
    body: data.body || 'You have a new notification',
    icon: '/assets/icons/icon-192.png',
    badge: '/assets/icons/icon-72.png',
    vibrate: [100, 50, 100],
    tag: data.tag || 'poolai-notification',
    renotify: true,
    data: {
      url: data.url || '/dashboard.php',
      timestamp: Date.now()
    },
    actions: [
      { action: 'open', title: 'Open', icon: '/assets/icons/action-open.png' },
      { action: 'dismiss', title: 'Dismiss', icon: '/assets/icons/action-dismiss.png' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'PoolAIssistant', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const urlToOpen = event.notification.data?.url || '/dashboard.php';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Focus existing window if available
        for (const client of clientList) {
          if (client.url.includes(location.origin) && 'focus' in client) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        // Open new window
        return clients.openWindow(urlToOpen);
      })
  );
});

self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification closed:', event.notification.tag);
});

// Periodic background sync (where supported)
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'update-device-status') {
    event.waitUntil(updateDeviceStatus());
  }
});

async function updateDeviceStatus() {
  console.log('[SW] Periodic sync: updating device status');
  // Fetch latest device status for offline access
}

console.log('[SW] Service worker loaded:', CACHE_VERSION);
