<?php
/**
 * PoolAIssistant Smart Link
 *
 * URL: /go.php?d=<device_uuid>
 *
 * Routes a phone scan to the right place:
 *   - Phone has a known local Pi (localStorage IP set via the PWA's local Pi
 *     settings) and it's reachable → http://<local-ip>/.
 *   - Otherwise → cloud device detail page (login first if needed).
 *
 * Important: we deliberately do NOT use the Pi's last-heartbeat IP here. That
 * IP is reported to the cloud every 15 minutes, so it goes stale within one
 * DHCP renewal — and we saw exactly that fail in production. The local-Pi IP
 * is now strictly "something the user typed once into THEIR phone", which is
 * either correct or absent. Absent = we just go cloud, no harm done.
 */

require_once __DIR__ . '/config/database.php';
require_once __DIR__ . '/includes/PortalAuth.php';

session_start();

$uuid = trim((string)($_GET['d'] ?? ''));

// Soft validation — UUIDs are 36 chars with dashes, but be lenient about case.
if ($uuid === '' || !preg_match('/^[a-f0-9-]{32,40}$/i', $uuid)) {
    http_response_code(400);
    header('Location: /dashboard.php');
    exit;
}

$pdo = db();

// Resolve uuid → numeric id + alias only. We deliberately don't look up the
// last-known LAN IP — it's stale far too often to drive routing decisions.
$stmt = $pdo->prepare("
    SELECT id AS device_id, name AS alias
    FROM pi_devices
    WHERE device_uuid = ?
    LIMIT 1
");
$stmt->execute([$uuid]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$device) {
    header('Location: /dashboard.php');
    exit;
}

$deviceId = (int)$device['device_id'];
$alias    = $device['alias'] ?: 'your pool';

$auth = new PortalAuth();
$isLoggedIn = $auth->isLoggedIn();

$cloudHref = '/device.php?id=' . $deviceId;
$loginHref = '/login.php?redirect=' . urlencode($cloudHref);
$fallback  = $isLoggedIn ? $cloudHref : $loginHref;
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>Connecting&hellip; - PoolAIssistant</title>

  <meta name="theme-color" content="#0066cc">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <link rel="manifest" href="/manifest.json">
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">

  <link rel="stylesheet" href="/assets/css/portal.css">
  <script src="/assets/js/pwa.js" defer></script>
  <style>
    .go-page {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      background: var(--bg-color);
    }
    .go-card {
      background: var(--card-bg);
      border-radius: var(--border-radius-lg);
      box-shadow: var(--shadow-lg);
      padding: 2.5rem 2rem;
      text-align: center;
      max-width: 420px;
      width: 100%;
    }
    .go-spinner {
      width: 48px;
      height: 48px;
      border: 4px solid var(--gray-200);
      border-top-color: var(--primary);
      border-radius: 50%;
      margin: 0 auto 1.25rem;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .go-title {
      font-size: 1.25rem;
      margin: 0 0 0.5rem;
      color: var(--primary);
    }
    .go-sub {
      color: var(--text-muted);
      font-size: 0.9375rem;
      margin: 0 0 1.5rem;
    }
    .go-actions { display: flex; flex-direction: column; gap: 0.5rem; }
    .go-btn {
      display: inline-block;
      background: var(--primary);
      color: white;
      text-decoration: none;
      padding: 0.75rem 1.25rem;
      border-radius: var(--border-radius);
      font-weight: 500;
      border: none;
      cursor: pointer;
    }
    .go-btn.secondary {
      background: transparent;
      color: var(--text-muted);
      border: 1px solid var(--border-color);
    }
    .go-btn:hover { background: var(--primary-hover); }
    .go-btn.secondary:hover { background: var(--gray-50); }
    .go-hint {
      margin-top: 1rem;
      font-size: 0.8125rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>
  <div class="go-page">
    <div class="go-card">
      <div class="go-spinner" id="goSpinner"></div>
      <h1 class="go-title">Connecting to <?= htmlspecialchars($alias) ?>&hellip;</h1>
      <p class="go-sub" id="goSub">Looking for your Pi on this network.</p>

      <div class="go-actions">
        <a class="go-btn secondary" href="<?= htmlspecialchars($fallback) ?>">View in cloud portal</a>
      </div>

      <p class="go-hint" id="goHint"></p>
    </div>
  </div>

  <script>
    (function () {
      const fallback = <?= json_encode($fallback) ?>;
      const sub      = document.getElementById('goSub');
      const hint     = document.getElementById('goHint');
      const spin     = document.getElementById('goSpinner');

      function gotoFallback() { window.location.replace(fallback); }

      // Wait for pwa.js (loaded with defer) to register window.PoolAIPWA before
      // probing. checkLocalPi() reads the user-set localStorage IP from THIS
      // phone — it's never something the server knows about. Empty/absent =>
      // straight to cloud, which is the safe and right default.
      function waitForPwa(retries) {
        if (window.PoolAIPWA && typeof window.PoolAIPWA.checkLocalPi === 'function') {
          return runProbe();
        }
        if (retries <= 0) {
          // pwa.js never loaded — straight to cloud.
          gotoFallback();
          return;
        }
        setTimeout(() => waitForPwa(retries - 1), 100);
      }

      async function runProbe() {
        const settings = window.PoolAIPWA.getLocalPi
          ? window.PoolAIPWA.getLocalPi()
          : { ip: '' };

        if (!settings || !settings.ip) {
          // No local Pi configured on this phone — that's the common case for
          // a fresh scan. Cloud is the right destination.
          sub.textContent = 'Opening cloud portal…';
          setTimeout(gotoFallback, 400);
          return;
        }

        const result = await window.PoolAIPWA.checkLocalPi();
        if (result && result.reachable && result.baseUrl) {
          spin.style.display = 'none';
          sub.textContent = 'Found it. Opening your Pi…';
          window.location.replace(result.baseUrl + '/');
          return;
        }

        spin.style.display = 'none';
        sub.textContent = 'Not on the pool\'s network — showing cloud view…';
        hint.textContent = 'Tip: when you\'re on your pool\'s WiFi, the app can store the local Pi address in Settings.';
        setTimeout(gotoFallback, 1200);
      }

      waitForPwa(20);
    })();
  </script>
</body>
</html>
