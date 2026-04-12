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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
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
    </script>
</body>
</html>
