/**
 * PoolAIssistant PWA - Client-side functionality
 * Handles install prompts, local Pi connection, and offline support
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        LOCAL_TIMEOUT: 3000,       // Timeout for local Pi connection (ms)
        STORAGE_KEY_PI_IP: 'poolai_local_ip',
        STORAGE_KEY_PI_PORT: 'poolai_local_port',
        STORAGE_KEY_INSTALLED: 'poolai_pwa_installed'
    };

    // PWA Install handling
    let deferredPrompt = null;
    let installBanner = null;

    // Register service worker
    async function registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.register('/service-worker.js', {
                    scope: '/'
                });
                console.log('[PWA] Service Worker registered:', registration.scope);

                // Check for updates
                registration.addEventListener('updatefound', () => {
                    const newWorker = registration.installing;
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            showUpdateBanner();
                        }
                    });
                });

                return registration;
            } catch (error) {
                console.error('[PWA] Service Worker registration failed:', error);
            }
        }
        return null;
    }

    // Show update available banner
    function showUpdateBanner() {
        const banner = document.createElement('div');
        banner.className = 'pwa-update-banner';
        banner.innerHTML = `
            <span>A new version is available!</span>
            <button onclick="location.reload()">Update Now</button>
            <button onclick="this.parentElement.remove()">Later</button>
        `;
        document.body.appendChild(banner);
    }

    // Handle install prompt
    window.addEventListener('beforeinstallprompt', (e) => {
        console.log('[PWA] Install prompt available');
        e.preventDefault();
        deferredPrompt = e;

        // Don't show if already installed or dismissed recently
        if (localStorage.getItem(CONFIG.STORAGE_KEY_INSTALLED) === 'true') {
            return;
        }

        showInstallBanner();
    });

    // Create and show install banner
    function showInstallBanner() {
        if (installBanner) return;

        installBanner = document.createElement('div');
        installBanner.className = 'pwa-install-banner';
        installBanner.innerHTML = `
            <div class="pwa-install-content">
                <div class="pwa-install-icon">
                    <img src="/assets/icons/icon-72.png" alt="PoolAI" width="48" height="48" onerror="this.style.display='none'">
                </div>
                <div class="pwa-install-text">
                    <strong>Install PoolAIssistant</strong>
                    <span>Add to your home screen for quick access</span>
                </div>
            </div>
            <div class="pwa-install-actions">
                <button class="pwa-install-btn" id="pwaInstallBtn">Install</button>
                <button class="pwa-dismiss-btn" id="pwaDismissBtn">Not Now</button>
            </div>
        `;

        document.body.appendChild(installBanner);

        // Add event listeners
        document.getElementById('pwaInstallBtn').addEventListener('click', installPWA);
        document.getElementById('pwaDismissBtn').addEventListener('click', dismissInstallBanner);

        // Animate in
        setTimeout(() => installBanner.classList.add('visible'), 100);
    }

    // Install the PWA
    async function installPWA() {
        if (!deferredPrompt) {
            console.log('[PWA] No install prompt available');
            return;
        }

        // Show the install prompt
        deferredPrompt.prompt();

        // Wait for the user's response
        const { outcome } = await deferredPrompt.userChoice;
        console.log('[PWA] Install outcome:', outcome);

        if (outcome === 'accepted') {
            localStorage.setItem(CONFIG.STORAGE_KEY_INSTALLED, 'true');
        }

        deferredPrompt = null;
        dismissInstallBanner();
    }

    // Dismiss install banner
    function dismissInstallBanner() {
        if (installBanner) {
            installBanner.classList.remove('visible');
            setTimeout(() => {
                installBanner.remove();
                installBanner = null;
            }, 300);
        }
    }

    // Detect if running as installed PWA
    function isInstalledPWA() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    }

    // Track installed state
    window.addEventListener('appinstalled', () => {
        console.log('[PWA] App installed');
        localStorage.setItem(CONFIG.STORAGE_KEY_INSTALLED, 'true');
        dismissInstallBanner();
    });

    // ----- Local Pi Connection -----

    /**
     * Save local Pi connection settings
     */
    function saveLocalPiSettings(ip, port = 80) {
        localStorage.setItem(CONFIG.STORAGE_KEY_PI_IP, ip);
        localStorage.setItem(CONFIG.STORAGE_KEY_PI_PORT, port.toString());
    }

    /**
     * Get saved local Pi settings
     */
    function getLocalPiSettings() {
        return {
            ip: localStorage.getItem(CONFIG.STORAGE_KEY_PI_IP) || '',
            port: parseInt(localStorage.getItem(CONFIG.STORAGE_KEY_PI_PORT) || '80', 10)
        };
    }

    /**
     * Check if local Pi is reachable
     */
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
                    data: data,
                    url: `http://${settings.ip}:${settings.port}`
                };
            }
            return { reachable: false, reason: 'bad_response' };
        } catch (error) {
            return {
                reachable: false,
                reason: error.name === 'AbortError' ? 'timeout' : 'network_error',
                error: error.message
            };
        }
    }

    /**
     * Open local Pi interface
     */
    function openLocalPi() {
        const settings = getLocalPiSettings();
        if (settings.ip) {
            window.open(`http://${settings.ip}:${settings.port}`, '_blank');
        }
    }

    // ----- Connection Status UI -----

    /**
     * Create connection status indicator
     */
    function createConnectionStatus() {
        const status = document.createElement('div');
        status.id = 'pwaConnectionStatus';
        status.className = 'pwa-connection-status';
        status.innerHTML = `
            <span class="status-dot"></span>
            <span class="status-text">Checking...</span>
        `;
        return status;
    }

    /**
     * Update connection status UI
     */
    function updateConnectionStatus(state, message) {
        const status = document.getElementById('pwaConnectionStatus');
        if (!status) return;

        const dot = status.querySelector('.status-dot');
        const text = status.querySelector('.status-text');

        dot.className = 'status-dot ' + state;
        text.textContent = message;
    }

    // ----- iOS Install Instructions -----

    function showIOSInstallInstructions() {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        const isInStandaloneMode = window.navigator.standalone === true;

        if (isIOS && !isInStandaloneMode) {
            const banner = document.createElement('div');
            banner.className = 'pwa-ios-banner';
            banner.innerHTML = `
                <div class="pwa-ios-content">
                    <strong>Install PoolAIssistant</strong>
                    <p>Tap <span class="share-icon"></span> then "Add to Home Screen"</p>
                </div>
                <button class="pwa-ios-dismiss" onclick="this.parentElement.remove()">Got it</button>
            `;
            document.body.appendChild(banner);

            // Auto-dismiss after 10 seconds
            setTimeout(() => banner.remove(), 10000);
        }
    }

    // ----- Public API -----

    window.PoolAIPWA = {
        install: installPWA,
        isInstalled: isInstalledPWA,
        saveLocalPi: saveLocalPiSettings,
        getLocalPi: getLocalPiSettings,
        checkLocalPi: checkLocalPi,
        openLocalPi: openLocalPi,
        showInstallBanner: showInstallBanner
    };

    // ----- Initialize -----

    document.addEventListener('DOMContentLoaded', () => {
        // Register service worker
        registerServiceWorker();

        // Show iOS instructions if applicable
        setTimeout(showIOSInstallInstructions, 2000);

        // Add connection status to navbar if exists
        const navbar = document.querySelector('.navbar .nav-user');
        if (navbar) {
            const status = createConnectionStatus();
            navbar.insertBefore(status, navbar.firstChild);

            // Check local Pi status
            checkLocalPi().then(result => {
                if (result.reachable) {
                    updateConnectionStatus('online', 'Local');
                    status.style.cursor = 'pointer';
                    status.title = 'Click to open local Pi interface';
                    status.onclick = openLocalPi;
                } else if (result.reason === 'no_ip_configured') {
                    updateConnectionStatus('unknown', 'Cloud');
                } else {
                    updateConnectionStatus('offline', 'Cloud');
                }
            });
        }
    });

})();
