<?php
/**
 * PoolAIssistant Portal - Dashboard
 */

require_once __DIR__ . '/includes/PortalAuth.php';
require_once __DIR__ . '/includes/PortalDevices.php';

$auth = new PortalAuth();
$auth->requireAuth();

$user = $auth->getUser();
$devices = new PortalDevices($user['id']);
$deviceList = $devices->getDevices();

$error = '';
$success = '';

// Handle device linking
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action'])) {
    $csrf = $_POST['csrf_token'] ?? '';

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
    } else {
        switch ($_POST['action']) {
            case 'link_device':
                $linkCode = $_POST['link_code'] ?? '';
                $result = $devices->linkDevice($linkCode);
                if ($result['ok']) {
                    $success = $result['message'];
                    $deviceList = $devices->getDevices(); // Refresh list
                } else {
                    $error = $result['error'];
                }
                break;

            case 'unlink_device':
                $deviceId = $_POST['device_id'] ?? 0;
                $result = $devices->unlinkDevice($deviceId);
                if ($result['ok']) {
                    $success = $result['message'];
                    $deviceList = $devices->getDevices();
                } else {
                    $error = $result['error'];
                }
                break;

            case 'update_nickname':
                $deviceId = $_POST['device_id'] ?? 0;
                $nickname = $_POST['nickname'] ?? '';
                $result = $devices->updateNickname($deviceId, $nickname);
                if ($result['ok']) {
                    $success = 'Nickname updated';
                    $deviceList = $devices->getDevices();
                } else {
                    $error = $result['error'];
                }
                break;
        }
    }
}

$csrfToken = $auth->generateCSRFToken();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Dashboard - PoolAIssistant</title>

    <!-- PWA Meta Tags -->
    <meta name="theme-color" content="#0066cc">
    <meta name="description" content="Monitor and control your pool from anywhere">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="PoolAI">
    <meta name="application-name" content="PoolAIssistant">
    <meta name="msapplication-TileColor" content="#0066cc">
    <meta name="msapplication-config" content="/assets/icons/browserconfig.xml">

    <!-- PWA Manifest -->
    <link rel="manifest" href="/manifest.json">

    <!-- Favicon & Icons -->
    <link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/assets/icons/favicon-16.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">
    <link rel="mask-icon" href="/assets/icons/safari-pinned-tab.svg" color="#0066cc">

    <!-- Stylesheets -->
    <link rel="stylesheet" href="assets/css/portal.css">
    <style>
        /* Brief attention-pulse on the Local Pi panel when arrived via
           the #localPiSettings anchor (e.g. from go.php's hint). */
        @keyframes localPiPulse {
            0%   { box-shadow: 0 0 0 0 rgba(0, 102, 204, 0.45); }
            70%  { box-shadow: 0 0 0 14px rgba(0, 102, 204, 0); }
            100% { box-shadow: 0 0 0 0 rgba(0, 102, 204, 0); }
        }
        .local-pi-settings.pulse {
            animation: localPiPulse 1.6s ease-out;
        }
    </style>

    <!-- PWA Script -->
    <script src="/assets/js/pwa.js" defer></script>
</head>
<body>
    <nav class="navbar">
        <div class="nav-brand">
            <h1>PoolAIssistant</h1>
        </div>
        <div class="nav-user">
            <span><?= htmlspecialchars($user['name'] ?: $user['email']) ?></span>
            <a href="account.php" class="nav-link">Account</a>
            <a href="logout.php" class="nav-link">Logout</a>
        </div>
    </nav>

    <main class="dashboard-container">
        <div class="dashboard-header">
            <h2>Your Devices</h2>
            <button class="btn btn-primary" onclick="toggleLinkModal()">
                + Link New Device
            </button>
        </div>

        <?php if ($error): ?>
            <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <?php if ($success): ?>
            <div class="alert alert-success"><?= htmlspecialchars($success) ?></div>
        <?php endif; ?>

        <?php if (empty($deviceList)): ?>
            <div class="empty-state">
                <div class="empty-icon">📡</div>
                <h3>No Devices Linked</h3>
                <p>Link your first PoolAIssistant device to get started.</p>
                <button class="btn btn-primary" onclick="toggleLinkModal()">
                    Link a Device
                </button>
            </div>
        <?php else: ?>
            <div class="device-grid">
                <?php foreach ($deviceList as $device): ?>
                    <div class="device-card">
                        <div class="device-status status-<?= htmlspecialchars($device['status']) ?>">
                            <?= ucfirst(htmlspecialchars($device['status'])) ?>
                        </div>
                        <div class="device-info">
                            <h3 class="device-name">
                                <?= htmlspecialchars($device['nickname'] ?: $device['alias'] ?: 'Unnamed Device') ?>
                            </h3>
                            <p class="device-id">ID: <?= htmlspecialchars($device['device_uuid']) ?></p>
                            <?php if ($device['last_seen']): ?>
                                <p class="device-lastseen">
                                    Last seen: <?= date('d M Y H:i', strtotime($device['last_seen'])) ?>
                                </p>
                            <?php endif; ?>
                            <?php if ($device['software_version']): ?>
                                <p class="device-version">
                                    Version: <?= htmlspecialchars($device['software_version']) ?>
                                </p>
                            <?php endif; ?>
                        </div>
                        <div class="device-actions">
                            <a href="device.php?id=<?= $device['device_id'] ?>" class="btn btn-secondary">
                                View Data
                            </a>
                            <button class="btn btn-outline" onclick="showEditNickname(<?= $device['device_id'] ?>, '<?= htmlspecialchars(addslashes($device['nickname'] ?: '')) ?>')">
                                Rename
                            </button>
                            <?php if ($device['role'] === 'owner'): ?>
                                <button class="btn btn-danger-outline" onclick="confirmUnlink(<?= $device['device_id'] ?>)">
                                    Unlink
                                </button>
                            <?php endif; ?>
                        </div>
                    </div>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>

        <!-- Local Pi Connection Settings -->
        <div class="local-pi-settings" id="localPiSettings">
            <h4>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
                    <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
                    <path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path>
                    <line x1="12" y1="20" x2="12.01" y2="20"></line>
                </svg>
                Local Connection
            </h4>
            <p style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 1rem;">
                Connect directly to your Pi when on the same network for faster access.
            </p>
            <div class="local-pi-row">
                <div class="form-group">
                    <label for="localPiIp">Pi IP Address</label>
                    <input type="text" id="localPiIp" placeholder="e.g., 192.168.1.100"
                           pattern="^(\d{1,3}\.){3}\d{1,3}$">
                </div>
                <div class="form-group" style="max-width: 100px;">
                    <label for="localPiPort">Port</label>
                    <input type="number" id="localPiPort" value="80" min="1" max="65535">
                </div>
                <button class="btn btn-secondary" onclick="saveLocalPiSettings()">Save</button>
                <button class="btn btn-outline" onclick="testLocalConnection()">Test</button>
            </div>
            <div id="localPiStatus" style="margin-top: 0.75rem; display: none;"></div>
        </div>
    </main>

    <!-- Link Device Modal -->
    <div id="linkModal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Link a Device</h3>
                <button class="modal-close" onclick="toggleLinkModal()">&times;</button>
            </div>
            <div class="modal-body">
                <p>Enter the 6-digit link code shown on your PoolAIssistant device.</p>
                <form method="POST" id="linkForm">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">
                    <input type="hidden" name="action" value="link_device">
                    <div class="form-group">
                        <label for="link_code">Link Code</label>
                        <input type="text" id="link_code" name="link_code"
                               placeholder="ABC-123" maxlength="7"
                               pattern="[A-Za-z0-9]{3}-?[A-Za-z0-9]{3}"
                               class="link-code-input" required>
                    </div>
                    <button type="submit" class="btn btn-primary btn-block">Link Device</button>
                </form>
            </div>
        </div>
    </div>

    <!-- Edit Nickname Modal -->
    <div id="nicknameModal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Rename Device</h3>
                <button class="modal-close" onclick="closeNicknameModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST" id="nicknameForm">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">
                    <input type="hidden" name="action" value="update_nickname">
                    <input type="hidden" name="device_id" id="nickname_device_id" value="">
                    <div class="form-group">
                        <label for="nickname">Device Nickname</label>
                        <input type="text" id="nickname" name="nickname"
                               maxlength="100" required>
                    </div>
                    <button type="submit" class="btn btn-primary btn-block">Save</button>
                </form>
            </div>
        </div>
    </div>

    <!-- Unlink Confirmation Modal -->
    <div id="unlinkModal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Unlink Device</h3>
                <button class="modal-close" onclick="closeUnlinkModal()">&times;</button>
            </div>
            <div class="modal-body">
                <p>Are you sure you want to unlink this device? You can re-link it later with a new code.</p>
                <form method="POST" id="unlinkForm">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">
                    <input type="hidden" name="action" value="unlink_device">
                    <input type="hidden" name="device_id" id="unlink_device_id" value="">
                    <div class="modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeUnlinkModal()">Cancel</button>
                        <button type="submit" class="btn btn-danger">Unlink</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <script>
        function toggleLinkModal() {
            const modal = document.getElementById('linkModal');
            modal.style.display = modal.style.display === 'none' ? 'flex' : 'none';
        }

        function showEditNickname(deviceId, currentName) {
            document.getElementById('nickname_device_id').value = deviceId;
            document.getElementById('nickname').value = currentName;
            document.getElementById('nicknameModal').style.display = 'flex';
        }

        function closeNicknameModal() {
            document.getElementById('nicknameModal').style.display = 'none';
        }

        function confirmUnlink(deviceId) {
            document.getElementById('unlink_device_id').value = deviceId;
            document.getElementById('unlinkModal').style.display = 'flex';
        }

        function closeUnlinkModal() {
            document.getElementById('unlinkModal').style.display = 'none';
        }

        // Close modals when clicking outside
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) {
                if (e.target === this) {
                    this.style.display = 'none';
                }
            });
        });

        // Format link code input
        document.getElementById('link_code').addEventListener('input', function(e) {
            let value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            if (value.length > 3) {
                value = value.slice(0, 3) + '-' + value.slice(3, 6);
            }
            e.target.value = value;
        });

        // Local Pi Settings
        document.addEventListener('DOMContentLoaded', function() {
            // Load saved settings
            const settings = window.PoolAIPWA ? window.PoolAIPWA.getLocalPi() : {
                ip: localStorage.getItem('poolai_local_ip') || '',
                port: parseInt(localStorage.getItem('poolai_local_port') || '80', 10)
            };

            if (settings.ip) {
                document.getElementById('localPiIp').value = settings.ip;
            }
            document.getElementById('localPiPort').value = settings.port;

            // Pulse the panel + focus the IP input when arrived via #localPiSettings
            // anchor (e.g. from go.php's "save the Pi's address" hint). Browser does
            // the scroll itself; we just draw the eye and prep the form for input.
            if (window.location.hash === '#localPiSettings') {
                const panel = document.getElementById('localPiSettings');
                const ipInput = document.getElementById('localPiIp');
                if (panel) {
                    panel.classList.add('pulse');
                    setTimeout(() => panel.classList.remove('pulse'), 2000);
                }
                if (ipInput && !ipInput.value) ipInput.focus();
            }
        });

        function saveLocalPiSettings() {
            const ip = document.getElementById('localPiIp').value.trim();
            const port = parseInt(document.getElementById('localPiPort').value, 10) || 80;

            if (!ip) {
                showLocalPiStatus('Please enter an IP address.', 'error');
                return;
            }

            // Validate IP format
            const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;
            if (!ipPattern.test(ip)) {
                showLocalPiStatus('Invalid IP address format.', 'error');
                return;
            }

            if (window.PoolAIPWA) {
                window.PoolAIPWA.saveLocalPi(ip, port);
            } else {
                localStorage.setItem('poolai_local_ip', ip);
                localStorage.setItem('poolai_local_port', port.toString());
            }

            showLocalPiStatus('Settings saved!', 'success');
        }

        async function testLocalConnection() {
            const ip = document.getElementById('localPiIp').value.trim();
            const port = parseInt(document.getElementById('localPiPort').value, 10) || 80;

            if (!ip) {
                showLocalPiStatus('Please enter an IP address first.', 'error');
                return;
            }

            showLocalPiStatus('Testing connection...', 'info');

            try {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 5000);

                const response = await fetch(`http://${ip}:${port}/api/health`, {
                    method: 'GET',
                    mode: 'cors',
                    signal: controller.signal
                });

                clearTimeout(timeout);

                if (response.ok) {
                    const data = await response.json();
                    showLocalPiStatus(
                        `Connected! Version: ${data.version || 'Unknown'}`,
                        'success',
                        `<a href="http://${ip}:${port}" target="_blank" class="btn btn-primary" style="margin-top: 0.5rem;">Open Local Interface</a>`
                    );
                } else {
                    showLocalPiStatus('Device responded but returned an error.', 'error');
                }
            } catch (error) {
                if (error.name === 'AbortError') {
                    showLocalPiStatus('Connection timed out. Check the IP address and ensure you\'re on the same network.', 'error');
                } else {
                    showLocalPiStatus('Cannot connect. Make sure you\'re on the same network as the Pi.', 'error');
                }
            }
        }

        function showLocalPiStatus(message, type, extra = '') {
            const statusEl = document.getElementById('localPiStatus');
            const colors = {
                success: 'var(--success-color)',
                error: 'var(--danger-color)',
                info: 'var(--info-color)'
            };

            statusEl.innerHTML = `
                <div style="padding: 0.75rem; background: ${type === 'success' ? '#d4edda' : type === 'error' ? '#f8d7da' : '#d1ecf1'};
                            color: ${colors[type]}; border-radius: var(--border-radius); font-size: 0.875rem;">
                    ${message}
                    ${extra}
                </div>
            `;
            statusEl.style.display = 'block';

            if (type !== 'info') {
                setTimeout(() => {
                    if (!extra) statusEl.style.display = 'none';
                }, 5000);
            }
        }
    </script>
</body>
</html>
