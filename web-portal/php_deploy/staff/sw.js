/**
 * PoolAI Staff PWA service worker.
 * Shell-only cache so the app opens offline; all data requests go to network.
 */
const CACHE = 'poolai-staff-v1';
const SHELL = [
    '/staff/',
    '/staff/assets/styles.css',
    '/staff/assets/app.js',
    '/staff/manifest.json',
    '/staff/icon.php?size=192',
    '/staff/icon.php?size=512',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => {})
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(
            keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
        )).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;

    const url = new URL(req.url);
    if (url.origin !== self.location.origin) return;

    // Never cache API responses - we always want fresh data.
    if (url.pathname.startsWith('/staff/api/') || url.pathname.startsWith('/api/')) {
        return;
    }

    // Shell requests: cache-first with network fallback + background refresh.
    if (url.pathname.startsWith('/staff/')) {
        event.respondWith(
            caches.match(req).then((cached) => {
                const networked = fetch(req).then((res) => {
                    if (res && res.ok) {
                        const copy = res.clone();
                        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
                    }
                    return res;
                }).catch(() => cached);
                return cached || networked;
            })
        );
    }
});
