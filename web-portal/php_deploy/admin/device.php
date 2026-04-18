<?php
/**
 * PoolAIssistant Admin - Device Detail Page
 * Comprehensive device view with remote control capabilities
 */

// Uncomment for debugging:
// ini_set('display_errors', 1);
// error_reporting(E_ALL);

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AdminDevices.php';
require_once __DIR__ . '/../includes/RemoteSettings.php';

// Require admin login
requireAdmin();

$deviceId = intval($_GET['id'] ?? 0);
if ($deviceId <= 0) {
    header('Location: index.php');
    exit;
}

try {
    $adminDevices = new AdminDevices();
    $device = $adminDevices->getDevice($deviceId);

    if (!$device) {
        header('Location: index.php?error=device_not_found');
        exit;
    }

    $clients = $adminDevices->getDeviceClients($deviceId);
    $commandHistory = $adminDevices->getCommandHistory($deviceId, 20);
    $healthHistory = $adminDevices->getHealthHistory($deviceId, 10);
    $controllers = $adminDevices->getControllerStatus($deviceId);
    $alarms = $adminDevices->getCurrentAlarms($deviceId);

    // Pull the Pi's last-reported settings snapshot (added by the remote
    // settings feature). Safe if column hasn't been migrated yet.
    $settingsSnapshot = [];
    $settingsSnapshotAt = null;
    try {
        $snapStmt = db()->prepare("SELECT settings_snapshot_json, settings_snapshot_at
            FROM pi_devices WHERE id = ?");
        $snapStmt->execute([$deviceId]);
        if ($row = $snapStmt->fetch(PDO::FETCH_ASSOC)) {
            $settingsSnapshot = json_decode($row['settings_snapshot_json'] ?? '', true) ?: [];
            $settingsSnapshotAt = $row['settings_snapshot_at'];
        }
    } catch (PDOException $e) { /* column missing pre-migration - render empty */ }
} catch (Exception $e) {
    error_log("Device page error: " . $e->getMessage());
    // Initialize empty arrays on error
    $clients = [];
    $commandHistory = [];
    $healthHistory = [];
    $controllers = [];
    $alarms = [];
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($device['name'] ?: 'Device ' . $device['id']) ?> - PoolAIssistant Admin</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-2: #334155;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #475569;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }

        /* Header */
        .page-header {
            margin-bottom: 24px;
        }
        .back-link {
            color: var(--text-muted);
            text-decoration: none;
            font-size: 0.875rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            margin-bottom: 12px;
        }
        .back-link:hover { color: var(--text); }

        .device-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
        }
        .device-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .device-title h1 {
            font-size: 1.5rem;
            font-weight: 600;
        }
        .device-meta {
            display: flex;
            gap: 16px;
            margin-top: 8px;
            flex-wrap: wrap;
        }
        .device-meta span {
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .device-meta span strong { color: var(--text); }

        /* Status badges */
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 600;
        }
        .status-badge.online { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .status-badge.offline { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .status-badge.issues { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }
        .status-badge.online .status-dot { box-shadow: 0 0 8px var(--success); }

        /* Action buttons */
        .action-buttons {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            border: none;
            text-decoration: none;
            transition: all 0.15s;
        }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
        .btn-secondary { background: var(--surface-2); color: var(--text); }
        .btn-secondary:hover:not(:disabled) { background: var(--border); }
        .btn-warning { background: var(--warning); color: #000; }
        .btn-warning:hover:not(:disabled) { background: #d97706; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-danger:hover:not(:disabled) { background: #dc2626; }
        .btn-sm { padding: 6px 12px; font-size: 0.75rem; }

        /* Grid layout */
        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }
        @media (max-width: 1024px) {
            .grid-2 { grid-template-columns: 1fr; }
        }

        /* Cards */
        .card {
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
        }
        .card-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--surface-2);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .card-header h2 {
            font-size: 1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-header h2::before {
            content: '';
            width: 4px;
            height: 20px;
            background: var(--accent);
            border-radius: 2px;
        }
        .card-body { padding: 20px; }
        .card-body.no-padding { padding: 0; }

        /* Info grid */
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
        }
        .info-item {
            padding: 12px;
            background: var(--surface-2);
            border-radius: 8px;
        }
        .info-item .label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        .info-item .value {
            font-size: 1rem;
            font-weight: 500;
            word-break: break-all;
        }
        .info-item .value.mono {
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.875rem;
        }
        .info-item .value.large {
            font-size: 1.5rem;
            font-weight: 700;
        }

        /* Health indicators */
        .health-bar {
            height: 6px;
            background: var(--surface);
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }
        .health-bar-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s;
        }
        .health-bar-fill.green { background: var(--success); }
        .health-bar-fill.yellow { background: var(--warning); }
        .health-bar-fill.red { background: var(--danger); }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td { padding: 12px 16px; text-align: left; }
        th {
            background: var(--surface-2);
            font-weight: 600;
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tr:not(:last-child) td { border-bottom: 1px solid var(--surface-2); }
        tr:hover td { background: rgba(59, 130, 246, 0.05); }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge.success { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge.warning { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge.danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .badge.pending { background: rgba(59, 130, 246, 0.2); color: var(--accent); }
        .badge.neutral { background: var(--surface-2); color: var(--text-muted); }

        .mono { font-family: 'SF Mono', Monaco, monospace; }
        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.875rem; }
        .text-xs { font-size: 0.75rem; }

        /* Controllers grid */
        .controllers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 12px;
        }
        .controller-card {
            padding: 12px;
            background: var(--surface-2);
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .controller-status {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        .controller-status.online {
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
        }
        .controller-status.offline { background: var(--danger); }
        .controller-info { flex: 1; min-width: 0; }
        .controller-name {
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .controller-host {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-family: 'SF Mono', Monaco, monospace;
        }

        /* Issues list */
        .issue-item {
            padding: 12px;
            background: var(--surface-2);
            border-radius: 8px;
            margin-bottom: 8px;
            border-left: 3px solid var(--warning);
        }
        .issue-item:last-child { margin-bottom: 0; }
        .issue-item.critical { border-left-color: var(--danger); }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }

        /* Section spacing */
        .section { margin-bottom: 24px; }
        .section:last-child { margin-bottom: 0; }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.show { display: flex; }
        .modal {
            background: var(--surface);
            border-radius: 12px;
            max-width: 400px;
            width: 90%;
        }
        .modal-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--surface-2);
        }
        .modal-header h3 { font-size: 1.125rem; }
        .modal-body { padding: 20px; }
        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            padding: 16px 20px;
            border-top: 1px solid var(--surface-2);
        }

        /* Link styling */
        a { color: var(--accent); text-decoration: none; }
        a:hover { text-decoration: underline; }

        @media (max-width: 768px) {
            .container { padding: 12px; }
            .device-header { flex-direction: column; }
            .action-buttons { width: 100%; }
            .action-buttons .btn { flex: 1; justify-content: center; }
            th, td { padding: 8px 12px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Page Header -->
        <div class="page-header">
            <a href="index.php" class="back-link">&larr; Back to Devices</a>

            <div class="device-header">
                <div>
                    <div class="device-title">
                        <h1><?= htmlspecialchars($device['name'] ?: 'Device ' . $device['id']) ?></h1>
                        <span class="status-badge <?= $device['status'] ?>">
                            <span class="status-dot"></span>
                            <?= ucfirst($device['status']) ?>
                        </span>
                    </div>
                    <div class="device-meta">
                        <span>Version: <strong><?= htmlspecialchars($device['software_version'] ?? 'Unknown') ?></strong></span>
                        <span>IP: <strong class="mono"><?= htmlspecialchars($device['ip_address'] ?? '-') ?></strong></span>
                        <span>Last seen:
                            <strong>
                                <?php if ($device['minutes_ago'] !== null): ?>
                                    <?php if ($device['minutes_ago'] < 1): ?>
                                        Just now
                                    <?php elseif ($device['minutes_ago'] < 60): ?>
                                        <?= $device['minutes_ago'] ?> min ago
                                    <?php elseif ($device['minutes_ago'] < 1440): ?>
                                        <?= round($device['minutes_ago'] / 60) ?> hours ago
                                    <?php else: ?>
                                        <?= round($device['minutes_ago'] / 1440) ?> days ago
                                    <?php endif; ?>
                                <?php else: ?>
                                    Never
                                <?php endif; ?>
                            </strong>
                        </span>
                    </div>
                </div>

                <!-- Remote Control Buttons -->
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="sendCommand('upload')" id="btn-upload">
                        Request Upload
                    </button>
                    <button class="btn btn-warning" onclick="confirmCommand('restart', 'Restart Services')" id="btn-restart">
                        Restart Services
                    </button>
                    <button class="btn btn-secondary" onclick="confirmCommand('update', 'Check Updates')" id="btn-update">
                        Check Updates
                    </button>
                    <?php if ($device['has_issues']): ?>
                    <button class="btn btn-danger btn-sm" onclick="clearIssues()" id="btn-clear-issues">
                        Clear Issues
                    </button>
                    <?php endif; ?>
                </div>
            </div>
        </div>

        <!-- Two Column Layout -->
        <div class="grid-2">
            <!-- Left Column -->
            <div>
                <!-- Device Info Card -->
                <div class="card section">
                    <div class="card-header">
                        <h2>Device Information</h2>
                    </div>
                    <div class="card-body">
                        <div class="info-grid">
                            <div class="info-item">
                                <div class="label">Device UUID</div>
                                <div class="value mono text-sm"><?= htmlspecialchars(substr($device['device_uuid'] ?? '', 0, 12)) ?>...</div>
                            </div>
                            <div class="info-item">
                                <div class="label">API Key</div>
                                <div class="value mono text-sm"><?= htmlspecialchars($device['api_key_masked'] ?? '-') ?></div>
                            </div>
                            <div class="info-item">
                                <div class="label">Created</div>
                                <div class="value text-sm"><?= $device['created_at'] ? date('M j, Y', strtotime($device['created_at'])) : '-' ?></div>
                            </div>
                            <div class="info-item">
                                <div class="label">Status</div>
                                <div class="value">
                                    <span class="badge <?= $device['is_active'] ? 'success' : 'danger' ?>">
                                        <?= $device['is_active'] ? 'Active' : 'Inactive' ?>
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- System Health Card -->
                <div class="card section">
                    <div class="card-header">
                        <h2>System Health</h2>
                    </div>
                    <div class="card-body">
                        <div class="info-grid">
                            <div class="info-item">
                                <div class="label">CPU Temp</div>
                                <div class="value large"><?= $device['cpu_temp'] !== null ? number_format($device['cpu_temp'], 1) . '&deg;C' : '-' ?></div>
                                <?php if ($device['cpu_temp'] !== null): ?>
                                <div class="health-bar">
                                    <div class="health-bar-fill <?= $device['cpu_temp'] < 60 ? 'green' : ($device['cpu_temp'] < 75 ? 'yellow' : 'red') ?>"
                                         style="width: <?= min(100, $device['cpu_temp']) ?>%"></div>
                                </div>
                                <?php endif; ?>
                            </div>
                            <div class="info-item">
                                <div class="label">Memory</div>
                                <div class="value large"><?= $device['memory_used_pct'] !== null ? number_format($device['memory_used_pct'], 0) . '%' : '-' ?></div>
                                <?php if ($device['memory_used_pct'] !== null): ?>
                                <div class="health-bar">
                                    <div class="health-bar-fill <?= $device['memory_used_pct'] < 70 ? 'green' : ($device['memory_used_pct'] < 90 ? 'yellow' : 'red') ?>"
                                         style="width: <?= $device['memory_used_pct'] ?>%"></div>
                                </div>
                                <?php endif; ?>
                            </div>
                            <div class="info-item">
                                <div class="label">Disk</div>
                                <div class="value large"><?= $device['disk_used_pct'] !== null ? number_format($device['disk_used_pct'], 0) . '%' : '-' ?></div>
                                <?php if ($device['disk_used_pct'] !== null): ?>
                                <div class="health-bar">
                                    <div class="health-bar-fill <?= $device['disk_used_pct'] < 70 ? 'green' : ($device['disk_used_pct'] < 90 ? 'yellow' : 'red') ?>"
                                         style="width: <?= $device['disk_used_pct'] ?>%"></div>
                                </div>
                                <?php endif; ?>
                            </div>
                            <div class="info-item">
                                <div class="label">Uptime</div>
                                <div class="value large"><?= htmlspecialchars($device['uptime_display']) ?></div>
                            </div>
                            <div class="info-item">
                                <div class="label">Controllers</div>
                                <div class="value">
                                    <span style="color: var(--success)"><?= intval($device['controllers_online']) ?> online</span>
                                    <?php if ($device['controllers_offline'] > 0): ?>
                                    / <span style="color: var(--danger)"><?= intval($device['controllers_offline']) ?> offline</span>
                                    <?php endif; ?>
                                </div>
                            </div>
                            <div class="info-item">
                                <div class="label">Alarms</div>
                                <div class="value">
                                    <?php if ($device['alarms_total'] > 0): ?>
                                        <?php if ($device['alarms_critical'] > 0): ?>
                                        <span style="color: var(--danger)"><?= intval($device['alarms_critical']) ?> critical</span>
                                        <?php endif; ?>
                                        <?php if ($device['alarms_warning'] > 0): ?>
                                        <span style="color: var(--warning)"><?= intval($device['alarms_warning']) ?> warning</span>
                                        <?php endif; ?>
                                    <?php else: ?>
                                        <span style="color: var(--success)">None</span>
                                    <?php endif; ?>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Controllers Grid -->
                <?php if (!empty($controllers) || !empty($device['controllers'])): ?>
                <div class="card section">
                    <div class="card-header">
                        <h2>Controllers</h2>
                    </div>
                    <div class="card-body">
                        <div class="controllers-grid">
                            <?php
                            $controllerList = !empty($controllers) ? $controllers : $device['controllers'];
                            foreach ($controllerList as $ctrl):
                                $isOnline = isset($ctrl['is_online']) ? $ctrl['is_online'] : ($ctrl['online'] ?? false);
                            ?>
                            <div class="controller-card">
                                <div class="controller-status <?= $isOnline ? 'online' : 'offline' ?>"></div>
                                <div class="controller-info">
                                    <div class="controller-name"><?= htmlspecialchars($ctrl['name'] ?? 'Unknown') ?></div>
                                    <div class="controller-host"><?= htmlspecialchars($ctrl['host'] ?? '') ?></div>
                                </div>
                            </div>
                            <?php endforeach; ?>
                        </div>
                    </div>
                </div>
                <?php endif; ?>

                <!-- Current Issues -->
                <?php if ($device['has_issues'] && !empty($device['issues'])): ?>
                <div class="card section">
                    <div class="card-header">
                        <h2>Current Issues</h2>
                    </div>
                    <div class="card-body">
                        <?php foreach ($device['issues'] as $issue): ?>
                        <div class="issue-item">
                            <?php if (is_array($issue)): ?>
                                <?php foreach ($issue as $key => $value): ?>
                                <div><strong><?= htmlspecialchars($key) ?>:</strong> <?= htmlspecialchars(is_string($value) ? $value : json_encode($value)) ?></div>
                                <?php endforeach; ?>
                            <?php else: ?>
                                <?= htmlspecialchars($issue) ?>
                            <?php endif; ?>
                        </div>
                        <?php endforeach; ?>
                    </div>
                </div>
                <?php endif; ?>

                <!-- Current Alarms -->
                <?php if (!empty($alarms)): ?>
                <div class="card section">
                    <div class="card-header">
                        <h2>Active Alarms</h2>
                    </div>
                    <div class="card-body no-padding">
                        <table>
                            <thead>
                                <tr>
                                    <th>Severity</th>
                                    <th>Alarm</th>
                                    <th>Pool</th>
                                    <th>Since</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($alarms as $alarm): ?>
                                <tr>
                                    <td>
                                        <span class="badge <?= $alarm['severity'] === 'critical' ? 'danger' : 'warning' ?>">
                                            <?= htmlspecialchars($alarm['severity']) ?>
                                        </span>
                                    </td>
                                    <td><?= htmlspecialchars($alarm['alarm_name']) ?></td>
                                    <td class="text-muted"><?= htmlspecialchars($alarm['pool'] ?: '-') ?></td>
                                    <td class="text-muted text-sm"><?= date('M j, H:i', strtotime($alarm['started_at'])) ?></td>
                                </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                    </div>
                </div>
                <?php endif; ?>
            </div>

            <!-- Right Column -->
            <div>
                <!-- Linked Clients -->
                <div class="card section">
                    <div class="card-header">
                        <h2>Linked Clients</h2>
                        <span class="badge neutral"><?= count($clients) ?></span>
                    </div>
                    <div class="card-body no-padding">
                        <?php if (empty($clients)): ?>
                        <div class="empty-state">
                            <p>No clients linked to this device</p>
                        </div>
                        <?php else: ?>
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Role</th>
                                    <th>Linked</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($clients as $client): ?>
                                <tr>
                                    <td>
                                        <a href="client_detail.php?id=<?= $client['id'] ?>">
                                            <?= htmlspecialchars($client['name'] ?: $client['email']) ?>
                                        </a>
                                        <?php if ($client['user_status'] === 'suspended'): ?>
                                        <span class="badge danger">Suspended</span>
                                        <?php endif; ?>
                                        <div class="text-muted text-xs"><?= htmlspecialchars($client['email']) ?></div>
                                    </td>
                                    <td>
                                        <span class="badge <?= $client['role'] === 'owner' ? 'success' : 'neutral' ?>">
                                            <?= htmlspecialchars($client['role']) ?>
                                        </span>
                                    </td>
                                    <td class="text-muted text-sm"><?= date('M j, Y', strtotime($client['linked_at'])) ?></td>
                                </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                        <?php endif; ?>
                    </div>
                </div>

                <!-- Remote Settings -->
                <?php
                $settingsSchema = RemoteSettings::schema();
                $bySection = [];
                foreach ($settingsSchema as $key => $def) {
                    $bySection[$def['section'] ?? 'Other'][$key] = $def;
                }
                ksort($bySection);
                ?>
                <div class="card section">
                    <div class="card-header" style="display:flex; justify-content:space-between; align-items:center;">
                        <h2>Remote Settings</h2>
                        <?php if ($settingsSnapshotAt): ?>
                            <span class="text-muted text-xs">
                                last reported <?= htmlspecialchars(date('M j H:i', strtotime($settingsSnapshotAt))) ?>
                            </span>
                        <?php else: ?>
                            <span class="text-muted text-xs">no snapshot yet - push or wait for next heartbeat</span>
                        <?php endif; ?>
                    </div>
                    <div class="card-body">
                        <p class="text-muted text-sm" style="margin-bottom: 12px;">
                            Changes apply on the device's next heartbeat
                            (~1 minute) and restart the Pi's web UI service.
                            Secrets, backend URL, and device identity are
                            deliberately not editable from here.
                        </p>
                        <form id="remote-settings-form">
                            <?php foreach ($bySection as $sectionName => $fields): ?>
                                <details <?= $sectionName === 'Cloud sync' ? 'open' : '' ?>
                                         style="margin-bottom: 12px; background: var(--surface-2); border-radius: 8px;">
                                    <summary style="padding: 10px 12px; cursor:pointer; font-weight: 600;">
                                        <?= htmlspecialchars($sectionName) ?>
                                    </summary>
                                    <div style="padding: 8px 12px 14px;">
                                        <?php foreach ($fields as $key => $def):
                                            $current = $settingsSnapshot[$key] ?? null;
                                            $id = 'rs_' . $key;
                                        ?>
                                        <div style="display:flex; align-items:center; justify-content:space-between;
                                                    gap:12px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                                            <label for="<?= $id ?>" style="flex:1;">
                                                <div><?= htmlspecialchars($def['label']) ?></div>
                                                <?php if ($current !== null): ?>
                                                <div class="text-muted text-xs">
                                                    current: <code><?= htmlspecialchars(is_bool($current) ? ($current ? 'true' : 'false') : (string)$current) ?></code>
                                                </div>
                                                <?php endif; ?>
                                            </label>
                                            <?php if ($def['type'] === 'bool'): ?>
                                                <select id="<?= $id ?>" name="<?= $key ?>" data-type="bool" style="min-width:100px;">
                                                    <option value="">(no change)</option>
                                                    <option value="1">true</option>
                                                    <option value="0">false</option>
                                                </select>
                                            <?php elseif ($def['type'] === 'choice'): ?>
                                                <select id="<?= $id ?>" name="<?= $key ?>" data-type="choice" style="min-width:140px;">
                                                    <option value="">(no change)</option>
                                                    <?php foreach ($def['options'] as $ov => $ol): ?>
                                                        <option value="<?= htmlspecialchars((string)$ov) ?>"><?= htmlspecialchars($ol) ?></option>
                                                    <?php endforeach; ?>
                                                </select>
                                            <?php elseif ($def['type'] === 'int'): ?>
                                                <input id="<?= $id ?>" name="<?= $key ?>" data-type="int"
                                                       type="number" min="<?= $def['min'] ?? '' ?>" max="<?= $def['max'] ?? '' ?>"
                                                       placeholder="(no change)" style="width:120px;">
                                            <?php elseif ($def['type'] === 'time'): ?>
                                                <input id="<?= $id ?>" name="<?= $key ?>" data-type="time"
                                                       type="time" placeholder="(no change)" style="width:120px;">
                                            <?php endif; ?>
                                        </div>
                                        <?php endforeach; ?>
                                    </div>
                                </details>
                            <?php endforeach; ?>
                            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px;">
                                <span id="remote-settings-result" class="text-sm text-muted"></span>
                                <button type="button" class="btn btn-primary" onclick="pushRemoteSettings()">
                                    Apply to device
                                </button>
                            </div>
                        </form>
                    </div>
                </div>

                <!-- Command History -->
                <div class="card section">
                    <div class="card-header">
                        <h2>Command History</h2>
                    </div>
                    <div class="card-body no-padding">
                        <?php if (empty($commandHistory)): ?>
                        <div class="empty-state">
                            <p>No commands sent to this device</p>
                        </div>
                        <?php else: ?>
                        <table>
                            <thead>
                                <tr>
                                    <th>Command</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Completed</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($commandHistory as $cmd): ?>
                                <tr>
                                    <td>
                                        <strong><?= htmlspecialchars($cmd['command_type']) ?></strong>
                                        <?php if (!empty($cmd['payload_data']['requested_by'])): ?>
                                        <div class="text-muted text-xs">by <?= htmlspecialchars($cmd['payload_data']['requested_by']) ?></div>
                                        <?php endif; ?>
                                    </td>
                                    <td>
                                        <?php
                                        $statusClasses = [
                                            'pending' => 'pending',
                                            'acknowledged' => 'warning',
                                            'completed' => 'success',
                                            'failed' => 'danger'
                                        ];
                                        $statusClass = isset($statusClasses[$cmd['status']]) ? $statusClasses[$cmd['status']] : 'neutral';
                                        ?>
                                        <span class="badge <?= $statusClass ?>"><?= htmlspecialchars($cmd['status']) ?></span>
                                    </td>
                                    <td class="text-muted text-sm"><?= date('M j, H:i', strtotime($cmd['created_at'])) ?></td>
                                    <td class="text-muted text-sm">
                                        <?= $cmd['completed_at'] ? date('M j, H:i', strtotime($cmd['completed_at'])) : '-' ?>
                                    </td>
                                </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                        <?php endif; ?>
                    </div>
                </div>

                <!-- Health History -->
                <div class="card section">
                    <div class="card-header">
                        <h2>Health History</h2>
                    </div>
                    <div class="card-body no-padding">
                        <?php if (empty($healthHistory)): ?>
                        <div class="empty-state">
                            <p>No health records</p>
                        </div>
                        <?php else: ?>
                        <table>
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>CPU</th>
                                    <th>Mem</th>
                                    <th>Disk</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($healthHistory as $h): ?>
                                <tr>
                                    <td class="text-sm"><?= date('M j, H:i', strtotime($h['ts'])) ?></td>
                                    <td class="text-sm"><?= $h['cpu_temp'] !== null ? number_format($h['cpu_temp'], 1) . '&deg;' : '-' ?></td>
                                    <td class="text-sm"><?= $h['memory_used_pct'] !== null ? number_format($h['memory_used_pct'], 0) . '%' : '-' ?></td>
                                    <td class="text-sm"><?= $h['disk_used_pct'] !== null ? number_format($h['disk_used_pct'], 0) . '%' : '-' ?></td>
                                    <td>
                                        <?php if ($h['has_issues']): ?>
                                        <span class="badge warning">Issues</span>
                                        <?php elseif ($h['alarms_critical'] > 0): ?>
                                        <span class="badge danger">Critical</span>
                                        <?php else: ?>
                                        <span class="badge success">OK</span>
                                        <?php endif; ?>
                                    </td>
                                </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                        <?php endif; ?>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Confirmation Modal -->
    <div class="modal-overlay" id="confirmModal" onclick="if(event.target===this)closeModal()">
        <div class="modal">
            <div class="modal-header">
                <h3 id="confirmTitle">Confirm Action</h3>
            </div>
            <div class="modal-body">
                <p id="confirmMessage">Are you sure you want to perform this action?</p>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                <button class="btn btn-primary" id="confirmBtn" onclick="executeConfirmedCommand()">Confirm</button>
            </div>
        </div>
    </div>

    <script>
    const deviceId = <?= $deviceId ?>;
    let pendingCommand = null;

    function sendCommand(command) {
        const btn = document.getElementById('btn-' + command);
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Sending...';
        }

        fetch('/api/admin_device_command.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, command: command })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                alert(data.message);
                location.reload();
            } else {
                alert('Failed: ' + (data.error || 'Unknown error'));
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = getButtonLabel(command);
                }
            }
        })
        .catch(err => {
            alert('Network error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = getButtonLabel(command);
            }
        });
    }

    function getButtonLabel(command) {
        const labels = {
            'upload': 'Request Upload',
            'restart': 'Restart Services',
            'update': 'Check Updates'
        };
        return labels[command] || command;
    }

    function confirmCommand(command, label) {
        pendingCommand = command;
        document.getElementById('confirmTitle').textContent = 'Confirm: ' + label;

        const messages = {
            'restart': 'This will restart the PoolAIssistant logger service on the Pi. The device will be briefly offline during restart.',
            'update': 'This will check for and apply any available software updates. The device may restart if an update is found.'
        };

        document.getElementById('confirmMessage').textContent = messages[command] || 'Are you sure you want to ' + label.toLowerCase() + '?';
        document.getElementById('confirmModal').classList.add('show');
    }

    function closeModal() {
        document.getElementById('confirmModal').classList.remove('show');
        pendingCommand = null;
    }

    function executeConfirmedCommand() {
        if (pendingCommand) {
            closeModal();
            sendCommand(pendingCommand);
        }
    }

    function clearIssues() {
        if (!confirm('Clear issues for this device? This will mark the device as healthy until the next heartbeat.')) return;

        const btn = document.getElementById('btn-clear-issues');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Clearing...';
        }

        fetch('/api/clear_device_issues.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                location.reload();
            } else {
                alert('Failed: ' + (data.error || 'Unknown error'));
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Clear Issues';
                }
            }
        })
        .catch(err => {
            alert('Network error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Clear Issues';
            }
        });
    }

    // Auto-refresh every 60 seconds
    setTimeout(() => location.reload(), 60000);

    // ---- Remote Settings push ----
    function pushRemoteSettings() {
        const form = document.getElementById('remote-settings-form');
        const result = document.getElementById('remote-settings-result');
        const deviceId = <?= (int)$deviceId ?>;
        const settings = {};

        form.querySelectorAll('[name][data-type]').forEach((el) => {
            const v = el.value;
            if (v === '' || v === null) return;
            const t = el.dataset.type;
            if (t === 'bool') settings[el.name] = v === '1';
            else if (t === 'int') settings[el.name] = parseInt(v, 10);
            else settings[el.name] = v;
        });

        if (Object.keys(settings).length === 0) {
            result.textContent = 'No changes to apply.';
            result.style.color = 'var(--warning)';
            return;
        }

        result.textContent = 'Queueing...';
        result.style.color = 'var(--text-muted)';

        fetch('/api/admin_update_setting.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ device_id: deviceId, settings }),
        })
        .then((r) => r.json())
        .then((data) => {
            if (data.ok) {
                result.textContent = 'Queued command #' + data.command_id +
                    ' for ' + data.applied_keys.length + ' setting(s).';
                result.style.color = 'var(--success)';
                setTimeout(() => location.reload(), 3000);
            } else {
                result.textContent = 'Failed: ' + (data.error || 'unknown');
                result.style.color = 'var(--danger)';
            }
        })
        .catch((err) => {
            result.textContent = 'Network error: ' + err.message;
            result.style.color = 'var(--danger)';
        });
    }
    </script>
</body>
</html>
