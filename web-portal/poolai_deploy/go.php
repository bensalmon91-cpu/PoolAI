<?php
/**
 * PoolAIssistant Smart Link
 *
 * URL: /go.php?d=<device_uuid>
 *
 * Routes a phone scan to the right place:
 *   - Phone on the same LAN as the Pi → Pi's local web UI (http://<lan-ip>).
 *   - Phone off-network               → cloud device detail page (login first).
 *
 * Detection happens client-side via fetch(/api/ping) with a short timeout.
 * Mixed-content + Private Network Access (PNA) preflight is required for the
 * probe to succeed against http://<lan-ip>/api/ping from this HTTPS page; the
 * Pi answers OPTIONS with the right headers (see health.py). When the probe
 * fails (older browser, off-network, Pi unreachable) we fall back to the
 * cloud detail page; if not logged in we send the user to /login.php first.
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

// Resolve uuid → numeric id + last-known LAN IP. Mirrors the JOIN in
// PortalDevices::getDevice() but without the user-scoping (anon visitors
// must still get the probe page).
$stmt = $pdo->prepare("
    SELECT
        d.id            AS device_id,
        d.device_uuid   AS device_uuid,
        d.name          AS alias,
        h.ip_address    AS lan_ip
    FROM pi_devices d
    LEFT JOIN (
        SELECT device_id, ip_address
        FROM device_health h1
        WHERE ts = (SELECT MAX(ts) FROM device_health h2 WHERE h2.device_id = h1.device_id)
    ) h ON h.device_id = d.id
    WHERE d.device_uuid = ?
    LIMIT 1
");
$stmt->execute([$uuid]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$device) {
    // Unknown UUID — bounce to dashboard (will route to login if anon).
    header('Location: /dashboard.php');
    exit;
}

$lanIp     = $device['lan_ip'] ?: '';
$deviceId  = (int)$device['device_id'];
$alias     = $device['alias'] ?: 'your pool';

// Auth state for client-side branching. Don't enforce login yet — we want the
// probe to run for anonymous scans too, then walk them through login on the
// off-LAN branch.
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
    <div class="go-card" id="goCard">
      <div class="go-spinner" id="goSpinner"></div>
      <h1 class="go-title" id="goTitle">Connecting to <?= htmlspecialchars($alias) ?>&hellip;</h1>
      <p class="go-sub" id="goSub">Looking for your Pi on this network.</p>

      <div class="go-actions">
        <?php if ($lanIp): ?>
          <button class="go-btn" id="goLocalBtn" type="button">Open Pi locally</button>
        <?php endif; ?>
        <a class="go-btn secondary" id="goCloudLink" href="<?= htmlspecialchars($fallback) ?>">View in cloud portal</a>
      </div>

      <p class="go-hint" id="goHint"></p>
    </div>
  </div>

  <script>
    (function () {
      const lanIp     = <?= json_encode($lanIp) ?>;
      const cloudHref = <?= json_encode($cloudHref) ?>;
      const loginHref = <?= json_encode($loginHref) ?>;
      const fallback  = <?= json_encode($fallback) ?>;
      const isAuthed  = <?= $isLoggedIn ? 'true' : 'false' ?>;

      const PROBE_TIMEOUT_MS = 2500;

      const sub   = document.getElementById('goSub');
      const hint  = document.getElementById('goHint');
      const btn   = document.getElementById('goLocalBtn');
      const link  = document.getElementById('goCloudLink');
      const spin  = document.getElementById('goSpinner');

      function gotoLocal() {
        window.location.replace('http://' + lanIp + '/');
      }

      function gotoFallback() {
        window.location.replace(fallback);
      }

      // Manual local-open. User-initiated nav can break out of mixed-content
      // probe restrictions even when the probe itself was blocked.
      if (btn) btn.addEventListener('click', gotoLocal);

      // No known LAN IP for this device → straight to cloud/login.
      if (!lanIp) {
        sub.textContent = 'Opening cloud portal…';
        setTimeout(gotoFallback, 400);
        return;
      }

      async function probe() {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
        try {
          const r = await fetch('http://' + lanIp + '/api/ping', {
            method: 'GET',
            mode: 'cors',
            cache: 'no-store',
            signal: ctrl.signal
          });
          clearTimeout(t);
          return r.ok;
        } catch (e) {
          clearTimeout(t);
          return false;
        }
      }

      probe().then(ok => {
        if (ok) {
          spin.style.display = 'none';
          sub.textContent = 'Found it. Opening your Pi…';
          gotoLocal();
          return;
        }
        // Probe failed — could be off-network, blocked by mixed content (older
        // browser without PNA support), or the Pi is genuinely down. Either
        // way, the cloud portal still has the latest synced data.
        spin.style.display = 'none';
        sub.textContent = isAuthed
          ? 'Not on this network — showing cloud view…'
          : 'Sign in to view your pool from anywhere.';
        hint.textContent = 'Tap "Open Pi locally" if you know the Pi is on this network.';
        setTimeout(gotoFallback, 1200);
      });
    })();
  </script>
</body>
</html>
