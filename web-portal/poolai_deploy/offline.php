<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>Offline - PoolAIssistant</title>
  <meta name="theme-color" content="#0066cc">
  <link rel="stylesheet" href="/assets/css/portal.css">
  <style>
    .offline-page {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: var(--space-6);
      background: var(--bg-color);
      text-align: center;
    }

    .offline-container {
      max-width: 400px;
    }

    .offline-icon {
      width: 80px;
      height: 80px;
      margin: 0 auto var(--space-6);
      background: var(--gray-100);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .offline-icon svg {
      width: 40px;
      height: 40px;
      color: var(--text-muted);
    }

    .offline-title {
      font-size: 1.5rem;
      margin-bottom: var(--space-3);
      color: var(--gray-900);
    }

    .offline-message {
      color: var(--text-muted);
      margin-bottom: var(--space-6);
      line-height: 1.6;
    }

    .offline-actions {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
    }

    .retry-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: var(--space-2);
      padding: var(--space-3) var(--space-6);
      background: var(--primary);
      color: white;
      border: none;
      border-radius: var(--border-radius);
      font-size: 1rem;
      font-weight: 500;
      cursor: pointer;
      transition: background var(--transition-fast);
    }

    .retry-btn:hover {
      background: var(--primary-hover);
    }

    .status-indicator {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: var(--space-2);
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-top: var(--space-4);
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--danger);
    }

    .status-dot.online {
      background: var(--success);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    .cached-data {
      margin-top: var(--space-8);
      padding: var(--space-4);
      background: var(--card-bg);
      border-radius: var(--border-radius);
      border: 1px solid var(--border-color);
      text-align: left;
    }

    .cached-data h3 {
      font-size: 0.875rem;
      margin-bottom: var(--space-3);
      color: var(--text-color);
    }

    .cached-data ul {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .cached-data li {
      padding: var(--space-2) 0;
      font-size: 0.875rem;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border-color);
    }

    .cached-data li:last-child {
      border-bottom: none;
    }
  </style>
</head>
<body>
  <div class="offline-page">
    <div class="offline-container">
      <div class="offline-icon">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.5 6.5L12 5l4 4M5.5 10.5L1 15l3 3m4-4l-3 3m7-7l4 4m-4-4L8 15m4-4l4 4m-4-4l-4 4"/>
          <path stroke-linecap="round" stroke-linejoin="round" d="M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856a8.25 8.25 0 0110.678-.556M1.924 8.674a11.25 11.25 0 0115.463-.832"/>
        </svg>
      </div>

      <h1 class="offline-title">You're Offline</h1>
      <p class="offline-message">
        It looks like you've lost your internet connection. Some features may be unavailable until you're back online.
      </p>

      <div class="offline-actions">
        <button class="retry-btn" onclick="location.reload()">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
          Try Again
        </button>
      </div>

      <div class="status-indicator">
        <span class="status-dot" id="status-dot"></span>
        <span id="status-text">Checking connection...</span>
      </div>

      <div class="cached-data" id="cached-data" style="display: none;">
        <h3>Available Offline</h3>
        <ul id="cached-list"></ul>
      </div>
    </div>
  </div>

  <script>
    // Check online status
    function updateOnlineStatus() {
      const dot = document.getElementById('status-dot');
      const text = document.getElementById('status-text');

      if (navigator.onLine) {
        dot.classList.add('online');
        text.textContent = 'Connection restored! Redirecting...';
        setTimeout(() => {
          window.location.href = '/dashboard.php';
        }, 1500);
      } else {
        dot.classList.remove('online');
        text.textContent = 'No internet connection';
      }
    }

    // Listen for online/offline events
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);

    // Initial check
    updateOnlineStatus();

    // Check cached pages
    if ('caches' in window) {
      caches.open('poolai-static-v2').then(cache => {
        cache.keys().then(keys => {
          const cachedPages = keys
            .filter(req => req.url.endsWith('.php') || req.url.endsWith('.html'))
            .map(req => {
              const url = new URL(req.url);
              return url.pathname;
            });

          if (cachedPages.length > 0) {
            const list = document.getElementById('cached-list');
            const container = document.getElementById('cached-data');
            container.style.display = 'block';

            cachedPages.forEach(page => {
              const li = document.createElement('li');
              const link = document.createElement('a');
              link.href = page;
              link.textContent = page.replace('/', '').replace('.php', '').replace('.html', '') || 'Home';
              link.style.color = 'var(--primary)';
              link.style.textTransform = 'capitalize';
              li.appendChild(link);
              list.appendChild(li);
            });
          }
        });
      }).catch(() => {});
    }
  </script>
</body>
</html>
