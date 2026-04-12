<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>Install PoolAIssistant</title>

  <!-- PWA Meta Tags -->
  <meta name="theme-color" content="#0066cc">
  <meta name="description" content="Install PoolAIssistant on your device for quick access">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="PoolAI">

  <link rel="manifest" href="/manifest.json">
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">
  <link rel="stylesheet" href="/assets/css/portal.css">

  <style>
    .install-page {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background: linear-gradient(135deg, #0066cc 0%, #004d99 100%);
      color: white;
      padding: env(safe-area-inset-top, 0) env(safe-area-inset-right, 0) env(safe-area-inset-bottom, 0) env(safe-area-inset-left, 0);
    }

    .install-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      text-align: center;
      max-width: 500px;
      margin: 0 auto;
    }

    .app-icon {
      width: 120px;
      height: 120px;
      border-radius: 24px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
      margin-bottom: 2rem;
      background: white;
      padding: 20px;
    }

    .app-icon img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }

    .install-title {
      font-size: 2rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
      letter-spacing: -0.02em;
    }

    .install-subtitle {
      font-size: 1.125rem;
      opacity: 0.9;
      margin-bottom: 2rem;
      line-height: 1.5;
    }

    .install-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      background: white;
      color: #0066cc;
      padding: 1rem 2rem;
      border-radius: 12px;
      font-size: 1.125rem;
      font-weight: 600;
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
      transition: transform 0.2s, box-shadow 0.2s;
      width: 100%;
      max-width: 300px;
    }

    .install-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
    }

    .install-btn:active {
      transform: translateY(0);
    }

    .install-btn svg {
      width: 24px;
      height: 24px;
    }

    .install-instructions {
      background: rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(10px);
      border-radius: 16px;
      padding: 1.5rem;
      margin-top: 2rem;
      width: 100%;
      text-align: left;
    }

    .install-instructions h3 {
      font-size: 1rem;
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .install-step {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 1rem;
    }

    .install-step:last-child {
      margin-bottom: 0;
    }

    .step-number {
      width: 28px;
      height: 28px;
      background: white;
      color: #0066cc;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 0.875rem;
      flex-shrink: 0;
    }

    .step-text {
      padding-top: 2px;
      line-height: 1.5;
    }

    .step-text code {
      background: rgba(255, 255, 255, 0.2);
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.875rem;
    }

    .share-icon {
      display: inline-block;
      width: 20px;
      height: 20px;
      background: currentColor;
      -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='currentColor' viewBox='0 0 24 24'%3E%3Cpath d='M12 2l4 4h-3v8h-2V6H8l4-4zm8 10v10H4V12h2v8h12v-8h2z'/%3E%3C/svg%3E") no-repeat center;
      mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='currentColor' viewBox='0 0 24 24'%3E%3Cpath d='M12 2l4 4h-3v8h-2V6H8l4-4zm8 10v10H4V12h2v8h12v-8h2z'/%3E%3C/svg%3E") no-repeat center;
      vertical-align: middle;
    }

    .features-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1rem;
      margin-top: 2rem;
      width: 100%;
    }

    .feature-item {
      text-align: center;
      padding: 1rem 0.5rem;
    }

    .feature-icon {
      width: 40px;
      height: 40px;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 0.5rem;
    }

    .feature-icon svg {
      width: 24px;
      height: 24px;
    }

    .feature-text {
      font-size: 0.8125rem;
      opacity: 0.9;
    }

    .skip-link {
      margin-top: 2rem;
      color: rgba(255, 255, 255, 0.8);
      font-size: 0.875rem;
    }

    .skip-link a {
      color: white;
      text-decoration: underline;
    }

    /* Already installed state */
    .installed-state {
      display: none;
    }

    .installed-state .install-btn {
      background: #10b981;
      color: white;
    }

    /* Hide based on platform */
    .android-only, .ios-only, .desktop-only {
      display: none;
    }

    body.is-android .android-only { display: block; }
    body.is-ios .ios-only { display: block; }
    body.is-desktop .desktop-only { display: block; }

    /* Success animation */
    @keyframes checkmark {
      0% { transform: scale(0); }
      50% { transform: scale(1.2); }
      100% { transform: scale(1); }
    }

    .success-icon {
      animation: checkmark 0.5s ease-out;
    }
  </style>
</head>
<body>
  <div class="install-page">
    <div class="install-container">
      <!-- App Icon -->
      <div class="app-icon">
        <img src="/assets/icons/icon-192.png" alt="PoolAIssistant" onerror="this.src='/assets/icons/icon-96.png'">
      </div>

      <!-- Title -->
      <h1 class="install-title">PoolAIssistant</h1>
      <p class="install-subtitle">Install the app for quick access to your pool monitoring dashboard</p>

      <!-- Install Button (Android/Desktop with install prompt) -->
      <div id="installPrompt">
        <button class="install-btn" id="installBtn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Install App
        </button>
      </div>

      <!-- iOS Instructions -->
      <div class="install-instructions ios-only" id="iosInstructions">
        <h3>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
          </svg>
          Install on iPhone/iPad
        </h3>
        <div class="install-step">
          <span class="step-number">1</span>
          <span class="step-text">Tap the <span class="share-icon"></span> Share button in Safari</span>
        </div>
        <div class="install-step">
          <span class="step-number">2</span>
          <span class="step-text">Scroll down and tap <code>Add to Home Screen</code></span>
        </div>
        <div class="install-step">
          <span class="step-number">3</span>
          <span class="step-text">Tap <code>Add</code> to confirm</span>
        </div>
      </div>

      <!-- Android Instructions (fallback if no install prompt) -->
      <div class="install-instructions android-only" id="androidInstructions" style="display: none;">
        <h3>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.523 15.341a.7.7 0 0 1-.443.154h-.086a.7.7 0 0 1-.443-.154l-4.32-3.564a.7.7 0 0 1 0-1.078l4.32-3.564a.7.7 0 0 1 .886 0l.086.071 4.32 3.564a.7.7 0 0 1 0 1.078l-4.32 3.493z"/>
            <path d="M6.92 22.52a.867.867 0 0 1-.54-.18l-.16-.13L.86 18.35a.867.867 0 0 1 0-1.34l5.36-3.86.16-.13a.867.867 0 0 1 1.08 0l.16.13 5.36 3.86a.867.867 0 0 1 0 1.34l-5.36 3.86-.16.13a.867.867 0 0 1-.54.18z"/>
          </svg>
          Install on Android
        </h3>
        <div class="install-step">
          <span class="step-number">1</span>
          <span class="step-text">Tap the menu icon (three dots) in Chrome</span>
        </div>
        <div class="install-step">
          <span class="step-number">2</span>
          <span class="step-text">Tap <code>Install app</code> or <code>Add to Home screen</code></span>
        </div>
        <div class="install-step">
          <span class="step-number">3</span>
          <span class="step-text">Tap <code>Install</code> to confirm</span>
        </div>
      </div>

      <!-- Features -->
      <div class="features-grid">
        <div class="feature-item">
          <div class="feature-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div class="feature-text">Works Offline</div>
        </div>
        <div class="feature-item">
          <div class="feature-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
          </div>
          <div class="feature-text">Push Alerts</div>
        </div>
        <div class="feature-item">
          <div class="feature-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
          </div>
          <div class="feature-text">Fast Access</div>
        </div>
      </div>

      <!-- Skip Link -->
      <p class="skip-link">
        or <a href="/login.php">continue in browser</a>
      </p>
    </div>
  </div>

  <script>
    // Detect platform
    const ua = navigator.userAgent;
    const isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    const isAndroid = /Android/.test(ua);
    const isSafari = /Safari/.test(ua) && !/Chrome|CriOS/.test(ua);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;

    // Add platform class to body
    if (isIOS) {
      document.body.classList.add('is-ios');
    } else if (isAndroid) {
      document.body.classList.add('is-android');
    } else {
      document.body.classList.add('is-desktop');
    }

    // If already installed, redirect to dashboard
    if (isStandalone) {
      window.location.href = '/dashboard.php';
    }

    // Handle install prompt (Chrome/Edge/Android)
    let deferredPrompt = null;
    const installBtn = document.getElementById('installBtn');
    const installPrompt = document.getElementById('installPrompt');
    const androidInstructions = document.getElementById('androidInstructions');

    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;

      // Show the install button
      installPrompt.style.display = 'block';

      // Hide manual instructions on Android since we have the prompt
      if (isAndroid) {
        androidInstructions.style.display = 'none';
      }
    });

    installBtn.addEventListener('click', async () => {
      if (deferredPrompt) {
        // Show native install prompt
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;

        if (outcome === 'accepted') {
          // Redirect to dashboard after install
          setTimeout(() => {
            window.location.href = '/dashboard.php';
          }, 500);
        }

        deferredPrompt = null;
      } else if (isIOS) {
        // Scroll to iOS instructions
        document.getElementById('iosInstructions').scrollIntoView({ behavior: 'smooth' });
      } else if (isAndroid) {
        // Show Android manual instructions
        androidInstructions.style.display = 'block';
        androidInstructions.scrollIntoView({ behavior: 'smooth' });
      } else {
        // Desktop - redirect to login
        window.location.href = '/login.php';
      }
    });

    // If no install prompt after 3 seconds on Android, show manual instructions
    if (isAndroid) {
      setTimeout(() => {
        if (!deferredPrompt) {
          androidInstructions.style.display = 'block';
        }
      }, 3000);
    }

    // Track app installed event
    window.addEventListener('appinstalled', () => {
      console.log('App installed');
      // Show success state
      installBtn.innerHTML = `
        <svg class="success-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        Installed!
      `;
      installBtn.style.background = '#10b981';
      installBtn.style.color = 'white';

      // Redirect after a moment
      setTimeout(() => {
        window.location.href = '/dashboard.php';
      }, 1500);
    });
  </script>
</body>
</html>
