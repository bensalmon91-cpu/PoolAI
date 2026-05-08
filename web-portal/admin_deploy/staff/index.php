<?php
/**
 * Staff PWA shell
 *
 * Authenticates against admin_users (session); renders a mobile-first SPA
 * shell. All data is fetched via /staff/api/* and existing /api/ai/* endpoints.
 */

require_once __DIR__ . '/../includes/auth.php';

// Non-JSON redirect to login if not authenticated.
if (!isAdmin()) {
    header('Location: /staff/login.php');
    exit;
}

$username = htmlspecialchars($_SESSION['admin_username'] ?? 'staff');
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#0f172a">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="PoolAI Staff">
    <title>PoolAI Staff</title>
    <link rel="manifest" href="/staff/manifest.json">
    <link rel="icon" href="/staff/icon.php?size=192" type="image/png">
    <link rel="apple-touch-icon" href="/staff/icon.php?size=192">
    <link rel="stylesheet" href="/staff/assets/styles.css">
</head>
<body data-user="<?= $username ?>">
    <div id="app" class="app-shell">
        <header class="app-header">
            <button class="icon-btn" id="refreshBtn" aria-label="Refresh">&#x21bb;</button>
            <div class="app-title">Pool<span class="accent">AI</span> Staff</div>
            <a href="/staff/logout.php" class="icon-btn" aria-label="Logout">&#x23FB;</a>
        </header>

        <main id="view" class="view" aria-live="polite">
            <div class="loading">Loading&hellip;</div>
        </main>

        <nav class="tabbar" role="tablist">
            <a href="#/home" class="tab" data-tab="home">
                <span class="tab-ico">&#x2302;</span>
                <span class="tab-lbl">Home</span>
            </a>
            <a href="#/ai" class="tab" data-tab="ai">
                <span class="tab-ico">&#x2699;</span>
                <span class="tab-lbl">AI</span>
                <span class="tab-badge" id="aiBadge" hidden>0</span>
            </a>
            <a href="#/checkin" class="tab" data-tab="checkin">
                <span class="tab-ico">&#x2713;</span>
                <span class="tab-lbl">Check-in</span>
            </a>
            <a href="#/devices" class="tab" data-tab="devices">
                <span class="tab-ico">&#x25A3;</span>
                <span class="tab-lbl">Devices</span>
            </a>
        </nav>

        <div id="toast" class="toast" hidden></div>
    </div>

    <script src="/staff/assets/app.js"></script>
    <script>
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/staff/sw.js').catch(() => {});
        });
    }
    </script>
</body>
</html>
