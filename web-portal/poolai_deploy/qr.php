<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Install QR Code - PoolAIssistant</title>
  <link rel="stylesheet" href="/assets/css/portal.css">
  <style>
    .qr-page {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      background: var(--bg-color);
    }

    .qr-container {
      background: var(--card-bg);
      border-radius: var(--border-radius-lg);
      box-shadow: var(--shadow-lg);
      padding: 3rem;
      text-align: center;
      max-width: 450px;
    }

    .qr-title {
      font-size: 1.5rem;
      margin-bottom: 0.5rem;
      color: var(--primary);
    }

    .qr-subtitle {
      color: var(--text-muted);
      margin-bottom: 2rem;
    }

    .qr-code {
      background: white;
      padding: 1.5rem;
      border-radius: var(--border-radius);
      display: inline-block;
      margin-bottom: 1.5rem;
      border: 1px solid var(--border-color);
    }

    .qr-code svg {
      display: block;
    }

    .qr-url {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      background: var(--gray-100);
      padding: 0.75rem 1rem;
      border-radius: var(--border-radius);
      margin-bottom: 1.5rem;
      font-family: var(--font-mono);
      font-size: 0.875rem;
      color: var(--text-muted);
      word-break: break-all;
    }

    .copy-btn {
      flex-shrink: 0;
      background: var(--primary);
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: var(--border-radius);
      font-size: 0.8125rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .copy-btn:hover {
      background: var(--primary-hover);
    }

    .copy-btn.copied {
      background: var(--success);
    }

    .instructions {
      text-align: left;
      padding: 1.5rem;
      background: var(--gray-50);
      border-radius: var(--border-radius);
      margin-bottom: 1.5rem;
    }

    .instructions h3 {
      font-size: 0.875rem;
      margin-bottom: 0.75rem;
      color: var(--text-color);
    }

    .instructions ol {
      margin: 0;
      padding-left: 1.25rem;
      color: var(--text-muted);
      font-size: 0.875rem;
    }

    .instructions li {
      margin-bottom: 0.5rem;
    }

    .download-options {
      display: flex;
      gap: 1rem;
      justify-content: center;
      flex-wrap: wrap;
    }

    .download-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.75rem 1.25rem;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      background: white;
      color: var(--text-color);
      font-weight: 500;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s;
      text-decoration: none;
    }

    .download-btn:hover {
      background: var(--gray-50);
      border-color: var(--gray-300);
    }

    .download-btn svg {
      width: 18px;
      height: 18px;
    }

    .back-link {
      margin-top: 1.5rem;
    }

    .back-link a {
      color: var(--text-muted);
      font-size: 0.875rem;
    }

    .install-here {
      display: none;
      margin-bottom: 1.5rem;
      padding: 1rem;
      background: var(--gray-50);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
    }

    .install-here.visible { display: block; }

    .install-here-title {
      font-size: 0.9375rem;
      font-weight: 500;
      margin-bottom: 0.25rem;
    }

    .install-here-sub {
      font-size: 0.8125rem;
      color: var(--text-muted);
      margin-bottom: 0.75rem;
    }

    .install-here-btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 0.625rem 1.25rem;
      border-radius: var(--border-radius);
      font-size: 0.9375rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .install-here-btn:hover { background: var(--primary-hover); }
  </style>
  <script src="/assets/js/pwa.js" defer></script>
</head>
<body>
  <div class="qr-page">
    <div class="qr-container">
      <h1 class="qr-title">Install PoolAIssistant</h1>
      <p class="qr-subtitle">Scan the QR code with your phone to install</p>

      <div class="install-here" id="installHere">
        <div class="install-here-title">Already on the phone you want to install on?</div>
        <div class="install-here-sub">Skip the scan and install directly.</div>
        <button class="install-here-btn" id="installHereBtn" type="button">Install on this phone</button>
      </div>

      <div class="qr-code" id="qrCode">
        <!-- QR code will be generated here -->
      </div>

      <div class="qr-url">
        <span id="installUrl"></span>
        <button class="copy-btn" id="copyBtn" onclick="copyUrl()">Copy</button>
      </div>

      <div class="instructions">
        <h3>How it works:</h3>
        <ol>
          <li>Open your phone's camera app</li>
          <li>Point it at the QR code above</li>
          <li>Tap the notification that appears</li>
          <li>Follow the prompts to install the app</li>
        </ol>
      </div>

      <div class="download-options">
        <button class="download-btn" onclick="downloadQR('png')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Download PNG
        </button>
        <button class="download-btn" onclick="printQR()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 6 2 18 2 18 9"/>
            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
            <rect x="6" y="14" width="12" height="8"/>
          </svg>
          Print
        </button>
      </div>

      <div class="back-link">
        <a href="/dashboard.php">&larr; Back to Dashboard</a>
      </div>
    </div>
  </div>

  <!-- QR Code Library -->
  <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>

  <script>
    // Get the install URL
    const baseUrl = window.location.origin;
    const installUrl = baseUrl + '/install.php';
    document.getElementById('installUrl').textContent = installUrl;

    // Generate QR code
    const qrContainer = document.getElementById('qrCode');

    QRCode.toCanvas(document.createElement('canvas'), installUrl, {
      width: 200,
      margin: 0,
      color: {
        dark: '#0066cc',
        light: '#ffffff'
      }
    }, function(error, canvas) {
      if (error) {
        console.error(error);
        qrContainer.innerHTML = '<p>Error generating QR code</p>';
        return;
      }

      // Also create SVG version for better quality
      QRCode.toString(installUrl, {
        type: 'svg',
        width: 200,
        margin: 0,
        color: {
          dark: '#0066cc',
          light: '#ffffff'
        }
      }, function(err, svg) {
        if (!err) {
          qrContainer.innerHTML = svg;
        } else {
          qrContainer.appendChild(canvas);
        }
      });
    });

    // Copy URL function
    function copyUrl() {
      const btn = document.getElementById('copyBtn');
      navigator.clipboard.writeText(installUrl).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = 'Copy';
          btn.classList.remove('copied');
        }, 2000);
      }).catch(err => {
        console.error('Failed to copy:', err);
        // Fallback
        const input = document.createElement('input');
        input.value = installUrl;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = 'Copy';
          btn.classList.remove('copied');
        }, 2000);
      });
    }

    // Download QR code as PNG
    function downloadQR(format) {
      QRCode.toDataURL(installUrl, {
        width: 400,
        margin: 2,
        color: {
          dark: '#0066cc',
          light: '#ffffff'
        }
      }, function(err, url) {
        if (err) {
          console.error(err);
          return;
        }

        const link = document.createElement('a');
        link.download = 'poolaissistant-install-qr.png';
        link.href = url;
        link.click();
      });
    }

    // Show "Install on this phone" panel when the browser fires
    // beforeinstallprompt. Hide if already installed (running standalone) or
    // if the prompt never fires within a short window (iOS Safari, desktop).
    (function setupInstallHere() {
      const panel = document.getElementById('installHere');
      const btn = document.getElementById('installHereBtn');
      if (!panel || !btn) return;

      function reveal() {
        if (window.PoolAIPWA && window.PoolAIPWA.isInstalled()) return;
        panel.classList.add('visible');
      }

      // Already firable when this script ran (rare race, but cheap to check).
      if (window.PoolAIPWA && window.PoolAIPWA.isInstallable()) {
        reveal();
      }

      // Future fires.
      window.addEventListener('pwa-installable', reveal);

      btn.addEventListener('click', async () => {
        if (!window.PoolAIPWA || !window.PoolAIPWA.isInstallable()) {
          // Fallback for browsers that never expose the prompt.
          alert('Tap your browser menu and choose "Add to Home Screen".');
          return;
        }
        const ok = await window.PoolAIPWA.install();
        if (ok) panel.classList.remove('visible');
      });
    })();

    // Print QR code
    function printQR() {
      const printWindow = window.open('', '_blank');
      const qrSvg = qrContainer.innerHTML;

      printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>PoolAIssistant Install QR</title>
          <style>
            body {
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              min-height: 100vh;
              margin: 0;
              padding: 2rem;
              text-align: center;
            }
            h1 {
              font-size: 1.5rem;
              color: #0066cc;
              margin-bottom: 0.5rem;
            }
            p {
              color: #666;
              margin-bottom: 2rem;
            }
            .qr {
              padding: 1rem;
              border: 2px solid #0066cc;
              border-radius: 8px;
              margin-bottom: 1rem;
            }
            .url {
              font-family: monospace;
              font-size: 0.875rem;
              color: #999;
            }
            @media print {
              body { min-height: auto; }
            }
          </style>
        </head>
        <body>
          <h1>PoolAIssistant</h1>
          <p>Scan to install the app</p>
          <div class="qr">${qrSvg}</div>
          <p class="url">${installUrl}</p>
        </body>
        </html>
      `);

      printWindow.document.close();
      printWindow.onload = function() {
        printWindow.print();
      };
    }
  </script>
</body>
</html>
