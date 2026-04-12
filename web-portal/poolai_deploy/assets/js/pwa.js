/**
 * PoolAIssistant PWA v2
 * Handles installation, offline support, service worker, and local Pi connection
 */

(function() {
  'use strict';

  // Configuration
  const CONFIG = {
    SW_PATH: '/service-worker.js',
    LOCAL_TIMEOUT: 3000,
    STORAGE_KEYS: {
      PI_IP: 'poolai_local_ip',
      PI_PORT: 'poolai_local_port',
      INSTALLED: 'poolai_pwa_installed',
      DISMISSED_AT: 'poolai_install_dismissed',
      THEME: 'poolai_theme'
    },
    DISMISS_COOLDOWN: 7 * 24 * 60 * 60 * 1000 // 7 days
  };

  // State
  let deferredPrompt = null;
  let installBanner = null;
  let swRegistration = null;

  // ==================== Service Worker ====================

  async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) {
      console.log('[PWA] Service workers not supported');
      return null;
    }

    try {
      const registration = await navigator.serviceWorker.register(CONFIG.SW_PATH, {
        scope: '/'
      });

      console.log('[PWA] Service Worker registered');
      swRegistration = registration;

      // Listen for updates
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (!newWorker) return;

        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateBanner();
          }
        });
      });

      // Listen for messages from SW
      navigator.serviceWorker.addEventListener('message', handleSWMessage);

      // Check for updates periodically
      setInterval(() => registration.update(), 60 * 60 * 1000); // Every hour

      return registration;
    } catch (error) {
      console.error('[PWA] Service Worker registration failed:', error);
      return null;
    }
  }

  function handleSWMessage(event) {
    const { type, data } = event.data || {};

    switch (type) {
      case 'SW_UPDATED':
        console.log('[PWA] Service worker updated to:', data?.version);
        break;
      case 'CACHE_UPDATED':
        console.log('[PWA] Cache updated');
        break;
    }
  }

  // ==================== Update Banner ====================

  function showUpdateBanner() {
    const existing = document.querySelector('.pwa-update-banner');
    if (existing) return;

    const banner = document.createElement('div');
    banner.className = 'pwa-update-banner';
    banner.innerHTML = `
      <span>A new version is available</span>
      <button onclick="window.PoolAIPWA.refresh()">Refresh</button>
      <button onclick="this.parentElement.remove()" style="background: transparent; border: none;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    `;
    document.body.prepend(banner);
  }

  function refresh() {
    if (swRegistration?.waiting) {
      swRegistration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
    window.location.reload();
  }

  // ==================== Install Prompt ====================

  window.addEventListener('beforeinstallprompt', (e) => {
    console.log('[PWA] Install prompt available');
    e.preventDefault();
    deferredPrompt = e;

    // Check if should show banner
    if (shouldShowInstallBanner()) {
      setTimeout(showInstallBanner, 1500);
    }
  });

  function shouldShowInstallBanner() {
    // Already installed
    if (isInstalledPWA()) return false;
    if (localStorage.getItem(CONFIG.STORAGE_KEYS.INSTALLED) === 'true') return false;

    // Recently dismissed
    const dismissedAt = localStorage.getItem(CONFIG.STORAGE_KEYS.DISMISSED_AT);
    if (dismissedAt) {
      const elapsed = Date.now() - parseInt(dismissedAt, 10);
      if (elapsed < CONFIG.DISMISS_COOLDOWN) return false;
    }

    return true;
  }

  function showInstallBanner() {
    if (installBanner || !deferredPrompt) return;

    installBanner = document.createElement('div');
    installBanner.className = 'pwa-install-banner';
    installBanner.innerHTML = `
      <div class="pwa-install-content">
        <div class="pwa-install-icon">
          <img src="/assets/icons/icon-72.png" alt="" width="40" height="40" loading="lazy">
        </div>
        <div class="pwa-install-text">
          <strong>Install PoolAIssistant</strong>
          <span>Quick access from your home screen</span>
        </div>
      </div>
      <div class="pwa-install-actions">
        <button class="pwa-install-btn" id="pwaInstallBtn">Install</button>
        <button class="pwa-dismiss-btn" id="pwaDismissBtn">Later</button>
      </div>
    `;

    document.body.appendChild(installBanner);

    document.getElementById('pwaInstallBtn').addEventListener('click', installPWA);
    document.getElementById('pwaDismissBtn').addEventListener('click', dismissInstallBanner);

    // Animate in
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        installBanner.classList.add('visible');
      });
    });
  }

  async function installPWA() {
    if (!deferredPrompt) {
      console.log('[PWA] No install prompt');
      return false;
    }

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;

    console.log('[PWA] Install outcome:', outcome);

    if (outcome === 'accepted') {
      localStorage.setItem(CONFIG.STORAGE_KEYS.INSTALLED, 'true');
      localStorage.removeItem(CONFIG.STORAGE_KEYS.DISMISSED_AT);
    }

    deferredPrompt = null;
    dismissInstallBanner();

    return outcome === 'accepted';
  }

  function dismissInstallBanner() {
    if (!installBanner) return;

    localStorage.setItem(CONFIG.STORAGE_KEYS.DISMISSED_AT, Date.now().toString());
    installBanner.classList.remove('visible');

    setTimeout(() => {
      installBanner?.remove();
      installBanner = null;
    }, 300);
  }

  window.addEventListener('appinstalled', () => {
    console.log('[PWA] App installed');
    localStorage.setItem(CONFIG.STORAGE_KEYS.INSTALLED, 'true');
    dismissInstallBanner();
  });

  // ==================== PWA Detection ====================

  function isInstalledPWA() {
    // Check display mode
    if (window.matchMedia('(display-mode: standalone)').matches) return true;
    if (window.matchMedia('(display-mode: fullscreen)').matches) return true;
    // iOS Safari
    if (window.navigator.standalone === true) return true;
    return false;
  }

  function isPWACapable() {
    return 'serviceWorker' in navigator && 'PushManager' in window;
  }

  // ==================== iOS Install Instructions ====================

  function showIOSInstallInstructions() {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    const isSafari = /Safari/.test(navigator.userAgent) && !/Chrome|CriOS/.test(navigator.userAgent);
    const isStandalone = window.navigator.standalone === true;

    if (!isIOS || !isSafari || isStandalone) return;

    // Check if recently dismissed
    const dismissedAt = localStorage.getItem('poolai_ios_dismissed');
    if (dismissedAt && Date.now() - parseInt(dismissedAt, 10) < CONFIG.DISMISS_COOLDOWN) return;

    const banner = document.createElement('div');
    banner.className = 'pwa-ios-banner';
    banner.innerHTML = `
      <div class="pwa-ios-content">
        <strong>Install PoolAIssistant</strong>
        <p>Tap <span class="share-icon"></span> then "Add to Home Screen"</p>
      </div>
      <button class="pwa-ios-dismiss">Got it</button>
    `;

    const dismissBtn = banner.querySelector('.pwa-ios-dismiss');
    dismissBtn.addEventListener('click', () => {
      localStorage.setItem('poolai_ios_dismissed', Date.now().toString());
      banner.remove();
    });

    document.body.appendChild(banner);
  }

  // ==================== Local Pi Connection ====================

  function saveLocalPiSettings(ip, port = 80) {
    localStorage.setItem(CONFIG.STORAGE_KEYS.PI_IP, ip.trim());
    localStorage.setItem(CONFIG.STORAGE_KEYS.PI_PORT, port.toString());
  }

  function getLocalPiSettings() {
    return {
      ip: localStorage.getItem(CONFIG.STORAGE_KEYS.PI_IP) || '',
      port: parseInt(localStorage.getItem(CONFIG.STORAGE_KEYS.PI_PORT) || '80', 10)
    };
  }

  function clearLocalPiSettings() {
    localStorage.removeItem(CONFIG.STORAGE_KEYS.PI_IP);
    localStorage.removeItem(CONFIG.STORAGE_KEYS.PI_PORT);
  }

  async function checkLocalPi() {
    const settings = getLocalPiSettings();
    if (!settings.ip) {
      return { reachable: false, reason: 'no_ip_configured' };
    }

    const url = `http://${settings.ip}:${settings.port}/api/health`;

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), CONFIG.LOCAL_TIMEOUT);

      const response = await fetch(url, {
        method: 'GET',
        mode: 'cors',
        signal: controller.signal
      });

      clearTimeout(timeout);

      if (response.ok) {
        const data = await response.json();
        return {
          reachable: true,
          data,
          baseUrl: `http://${settings.ip}:${settings.port}`
        };
      }

      return { reachable: false, reason: 'bad_response', status: response.status };
    } catch (error) {
      return {
        reachable: false,
        reason: error.name === 'AbortError' ? 'timeout' : 'network_error',
        error: error.message
      };
    }
  }

  function openLocalPi() {
    const settings = getLocalPiSettings();
    if (settings.ip) {
      window.open(`http://${settings.ip}:${settings.port}`, '_blank');
    }
  }

  // ==================== Connection Status ====================

  function createConnectionStatus() {
    const status = document.createElement('div');
    status.id = 'pwaConnectionStatus';
    status.className = 'pwa-connection-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.innerHTML = `
      <span class="status-dot" aria-hidden="true"></span>
      <span class="status-text">Checking...</span>
    `;
    return status;
  }

  function updateConnectionStatus(state, message) {
    const status = document.getElementById('pwaConnectionStatus');
    if (!status) return;

    const dot = status.querySelector('.status-dot');
    const text = status.querySelector('.status-text');

    dot.className = `status-dot ${state}`;
    text.textContent = message;
  }

  async function refreshConnectionStatus() {
    const result = await checkLocalPi();
    const status = document.getElementById('pwaConnectionStatus');

    if (result.reachable) {
      updateConnectionStatus('online', 'Local');
      if (status) {
        status.style.cursor = 'pointer';
        status.title = 'Connected to local Pi - Click to open';
        status.onclick = openLocalPi;
      }
    } else if (result.reason === 'no_ip_configured') {
      updateConnectionStatus('unknown', 'Cloud');
      if (status) {
        status.style.cursor = 'default';
        status.title = 'Using cloud connection';
        status.onclick = null;
      }
    } else {
      updateConnectionStatus('offline', 'Cloud');
      if (status) {
        status.style.cursor = 'default';
        status.title = 'Local Pi not reachable - Using cloud';
        status.onclick = null;
      }
    }

    return result;
  }

  // ==================== Online/Offline Detection ====================

  function handleOnlineStatus() {
    if (navigator.onLine) {
      document.body.classList.remove('is-offline');
      refreshConnectionStatus();
    } else {
      document.body.classList.add('is-offline');
      updateConnectionStatus('offline', 'Offline');
    }
  }

  window.addEventListener('online', handleOnlineStatus);
  window.addEventListener('offline', handleOnlineStatus);

  // ==================== Cache Management ====================

  async function clearAllCaches() {
    if (!('caches' in window)) return false;

    const keys = await caches.keys();
    await Promise.all(keys.map(key => caches.delete(key)));

    // Tell service worker to clear caches too
    if (swRegistration?.active) {
      const channel = new MessageChannel();
      swRegistration.active.postMessage({ type: 'CLEAR_CACHE' }, [channel.port2]);
    }

    return true;
  }

  async function getCacheSize() {
    if (!('caches' in window)) return 0;

    let totalSize = 0;
    const keys = await caches.keys();

    for (const key of keys) {
      const cache = await caches.open(key);
      const requests = await cache.keys();

      for (const request of requests) {
        const response = await cache.match(request);
        if (response) {
          const blob = await response.clone().blob();
          totalSize += blob.size;
        }
      }
    }

    return totalSize;
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  }

  // ==================== Public API ====================

  window.PoolAIPWA = {
    // Install
    install: installPWA,
    isInstalled: isInstalledPWA,
    isCapable: isPWACapable,
    showInstallBanner,
    dismissInstallBanner,

    // Service Worker
    refresh,
    getRegistration: () => swRegistration,

    // Local Pi
    saveLocalPi: saveLocalPiSettings,
    getLocalPi: getLocalPiSettings,
    clearLocalPi: clearLocalPiSettings,
    checkLocalPi,
    openLocalPi,

    // Connection
    refreshConnectionStatus,
    updateConnectionStatus,

    // Cache
    clearCache: clearAllCaches,
    getCacheSize,
    formatBytes,

    // Config
    config: CONFIG
  };

  // ==================== Initialize ====================

  document.addEventListener('DOMContentLoaded', () => {
    // Register service worker
    registerServiceWorker();

    // Handle initial online state
    handleOnlineStatus();

    // Add connection status to navbar
    const navbar = document.querySelector('.navbar .nav-user');
    if (navbar) {
      const status = createConnectionStatus();
      navbar.insertBefore(status, navbar.firstChild);
      refreshConnectionStatus();
    }

    // Show iOS instructions after delay
    setTimeout(showIOSInstallInstructions, 3000);

    // Mark as running as PWA
    if (isInstalledPWA()) {
      document.documentElement.classList.add('pwa-standalone');
    }

    console.log('[PWA] Initialized', {
      installed: isInstalledPWA(),
      capable: isPWACapable(),
      online: navigator.onLine
    });
  });

})();
