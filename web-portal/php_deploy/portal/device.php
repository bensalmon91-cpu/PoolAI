<?php
/**
 * PoolAIssistant Portal - Device Detail View
 */

require_once __DIR__ . '/../includes/PortalAuth.php';
require_once __DIR__ . '/../includes/PortalDevices.php';

$auth = new PortalAuth();
$auth->requireAuth();

$user = $auth->getUser();
$devicesManager = new PortalDevices($user['id']);

$deviceId = $_GET['id'] ?? 0;
$device = $devicesManager->getDevice($deviceId);

if (!$device) {
    header('Location: dashboard.php');
    exit;
}

// Fetch real data
$health = $devicesManager->getDeviceHealth($device['device_id']);
$suggestions = $devicesManager->getAISuggestions($device['device_id'], 5);
$responses = $devicesManager->getAIResponses($device['device_id'], 5);
$readings = $devicesManager->getLatestReadings($device['device_id']);
$currentAlarms = $devicesManager->getCurrentAlarms($device['device_id']);
$controllerStatus = $devicesManager->getControllerStatus($device['device_id']);
$pools = $devicesManager->getDevicePools($device['device_id']);

$csrfToken = $auth->generateCSRFToken();

// Helper function for time ago display
function timeAgo($datetime) {
    if (!$datetime) return 'Never';
    $now = new DateTime();
    $then = new DateTime($datetime);
    $diff = $now->diff($then);

    if ($diff->days > 0) return $diff->days . ' day' . ($diff->days > 1 ? 's' : '') . ' ago';
    if ($diff->h > 0) return $diff->h . ' hour' . ($diff->h > 1 ? 's' : '') . ' ago';
    if ($diff->i > 0) return $diff->i . ' min' . ($diff->i > 1 ? 's' : '') . ' ago';
    return 'Just now';
}

// Get the most recent reading timestamp for "last updated" display
$lastReadingTs = null;
foreach ($readings as $poolName => $metrics) {
    foreach ($metrics as $metric => $data) {
        if ($data['ts'] && (!$lastReadingTs || $data['ts'] > $lastReadingTs)) {
            $lastReadingTs = $data['ts'];
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($device['nickname'] ?: $device['alias'] ?: 'Device') ?> - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
    <style>
        .device-detail-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 2rem;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .device-detail-header h2 {
            margin: 0;
        }
        .device-meta {
            color: var(--text-muted);
            font-size: 0.875rem;
        }
        .data-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .data-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1.25rem;
            box-shadow: var(--shadow-sm);
        }
        .data-card-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }
        .data-card-value {
            font-size: 1.75rem;
            font-weight: 600;
        }
        .data-card-value.warning {
            color: #f59e0b;
        }
        .data-card-value.danger {
            color: #ef4444;
        }
        .data-card-value.success {
            color: #22c55e;
        }
        .data-card-unit {
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .section-title {
            font-size: 1.25rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border-color);
        }
        .placeholder-message {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 2rem;
            text-align: center;
            color: var(--text-muted);
        }
        .back-link {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
            color: var(--text-muted);
        }
        .back-link:hover {
            color: var(--primary-color);
        }
        .controllers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .controller-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1rem;
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        .controller-status {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .controller-status.online {
            background: #22c55e;
            box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
        }
        .controller-status.offline {
            background: #ef4444;
        }
        .controller-info {
            flex: 1;
        }
        .controller-host {
            font-weight: 500;
        }
        .controller-time {
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        .issues-list {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1rem;
            margin-bottom: 2rem;
        }
        .issue-item {
            padding: 0.75rem;
            border-left: 3px solid #f59e0b;
            background: rgba(245, 158, 11, 0.1);
            margin-bottom: 0.5rem;
            border-radius: 0 4px 4px 0;
        }
        .suggestion-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1rem;
            margin-bottom: 0.75rem;
            border-left: 3px solid var(--primary-color);
        }
        .suggestion-title {
            font-weight: 500;
            margin-bottom: 0.5rem;
        }
        .suggestion-body {
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .suggestion-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
        }
        .response-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1rem;
            margin-bottom: 0.75rem;
        }
        .response-question {
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }
        .response-answer {
            font-weight: 500;
        }
        .response-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
        }
        .two-column {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
        }
        @media (max-width: 768px) {
            .two-column {
                grid-template-columns: 1fr;
            }
        }

        /* Pool Readings Styles */
        .pool-section {
            margin-bottom: 2rem;
        }
        .pool-section-title {
            font-size: 1.125rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .pool-section-title::before {
            content: '';
            display: inline-block;
            width: 8px;
            height: 8px;
            background: var(--primary-color);
            border-radius: 50%;
        }
        .readings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
            gap: 1rem;
        }
        .reading-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1.25rem;
            box-shadow: var(--shadow-sm);
            position: relative;
            overflow: hidden;
        }
        .reading-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
        }
        .reading-card.status-green::before {
            background: #22c55e;
        }
        .reading-card.status-yellow::before {
            background: #f59e0b;
        }
        .reading-card.status-red::before {
            background: #ef4444;
        }
        .reading-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
            letter-spacing: 0.5px;
        }
        .reading-value {
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .reading-value.status-green {
            color: #22c55e;
        }
        .reading-value.status-yellow {
            color: #f59e0b;
        }
        .reading-value.status-red {
            color: #ef4444;
        }
        .reading-unit {
            font-size: 0.875rem;
            font-weight: 400;
            color: var(--text-muted);
        }
        .reading-time {
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
        }
        .last-updated-banner {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 0.75rem 1rem;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 0.875rem;
        }
        .last-updated-banner .pulse {
            width: 8px;
            height: 8px;
            background: #22c55e;
            border-radius: 50%;
            margin-right: 0.5rem;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .alarms-panel {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 1rem;
            margin-bottom: 1.5rem;
        }
        .alarm-item {
            padding: 0.75rem;
            border-left: 3px solid;
            margin-bottom: 0.5rem;
            border-radius: 0 4px 4px 0;
        }
        .alarm-item.critical {
            border-color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
        }
        .alarm-item.warning {
            border-color: #f59e0b;
            background: rgba(245, 158, 11, 0.1);
        }
        .alarm-item:last-child {
            margin-bottom: 0;
        }
        .alarm-source {
            font-weight: 500;
        }
        .alarm-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.25rem;
        }
        .no-data-message {
            color: var(--text-muted);
            text-align: center;
            padding: 2rem;
            background: var(--card-bg);
            border-radius: var(--border-radius);
        }
    </style>
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
        <a href="dashboard.php" class="back-link">&larr; Back to Devices</a>

        <div class="device-detail-header">
            <div>
                <h2><?= htmlspecialchars($device['nickname'] ?: $device['alias'] ?: 'Unnamed Device') ?></h2>
                <p class="device-meta">
                    <?php if ($device['software_version']): ?>
                        Version <?= htmlspecialchars($device['software_version']) ?> &bull;
                    <?php endif; ?>
                    <?php if ($device['ip_address']): ?>
                        <?= htmlspecialchars($device['ip_address']) ?> &bull;
                    <?php endif; ?>
                    <?php if ($device['last_seen']): ?>
                        Last seen: <?= date('d M Y H:i', strtotime($device['last_seen'])) ?>
                    <?php endif; ?>
                </p>
            </div>
            <div class="device-status status-<?= htmlspecialchars($device['status']) ?>">
                <?= ucfirst(htmlspecialchars($device['status'])) ?>
            </div>
        </div>

        <!-- Pool Readings Section -->
        <?php if (!empty($readings)): ?>
        <div class="last-updated-banner">
            <div style="display: flex; align-items: center;">
                <div class="pulse"></div>
                <span>Last updated: <?= $lastReadingTs ? timeAgo($lastReadingTs) : 'Unknown' ?></span>
            </div>
            <span style="color: var(--text-muted);">Auto-refresh in 60s</span>
        </div>

        <?php foreach ($readings as $poolName => $metrics): ?>
        <div class="pool-section">
            <?php if (count($readings) > 1): ?>
            <div class="pool-section-title"><?= htmlspecialchars($poolName) ?></div>
            <?php else: ?>
            <h3 class="section-title">Pool Readings</h3>
            <?php endif; ?>

            <div class="readings-grid">
                <?php
                // Define display order and labels
                $metricDisplay = [
                    'pH' => ['label' => 'pH', 'icon' => ''],
                    'Chlorine' => ['label' => 'Chlorine', 'icon' => ''],
                    'ORP' => ['label' => 'ORP', 'icon' => ''],
                    'Temperature' => ['label' => 'Temperature', 'icon' => ''],
                    'Temp' => ['label' => 'Temperature', 'icon' => ''],
                ];

                // Sort metrics with known ones first
                $sortedMetrics = [];
                foreach ($metricDisplay as $key => $info) {
                    foreach ($metrics as $metricName => $data) {
                        if (stripos($metricName, $key) !== false) {
                            $sortedMetrics[$metricName] = $data;
                        }
                    }
                }
                // Add any remaining metrics
                foreach ($metrics as $metricName => $data) {
                    if (!isset($sortedMetrics[$metricName])) {
                        $sortedMetrics[$metricName] = $data;
                    }
                }

                foreach ($sortedMetrics as $metricName => $data):
                    $status = $data['status'] ?? 'green';
                    $value = $data['value'] !== null ? number_format(floatval($data['value']), 2) : '--';
                    $unit = $data['unit'] ?? '';
                ?>
                <div class="reading-card status-<?= $status ?>">
                    <div class="reading-label"><?= htmlspecialchars($metricName) ?></div>
                    <div class="reading-value status-<?= $status ?>">
                        <?= $value ?>
                        <?php if ($unit): ?>
                        <span class="reading-unit"><?= htmlspecialchars($unit) ?></span>
                        <?php endif; ?>
                    </div>
                    <?php if ($data['ts']): ?>
                    <div class="reading-time"><?= timeAgo($data['ts']) ?></div>
                    <?php endif; ?>
                </div>
                <?php endforeach; ?>
            </div>
        </div>
        <?php endforeach; ?>
        <?php else: ?>
        <div class="no-data-message">
            <p>No pool readings available yet. Data will appear after the device uploads its first snapshot.</p>
        </div>
        <?php endif; ?>

        <!-- Active Alarms Section -->
        <?php if (!empty($currentAlarms)): ?>
        <h3 class="section-title">Active Alarms (<?= count($currentAlarms) ?>)</h3>
        <div class="alarms-panel">
            <?php foreach ($currentAlarms as $alarm): ?>
            <div class="alarm-item <?= htmlspecialchars($alarm['severity'] ?? 'warning') ?>">
                <div class="alarm-source"><?= htmlspecialchars($alarm['alarm_name'] ?: $alarm['alarm_source']) ?></div>
                <div class="alarm-meta">
                    <?php if ($alarm['pool']): ?>
                    <?= htmlspecialchars($alarm['pool']) ?> &bull;
                    <?php endif; ?>
                    Since <?= date('M j, H:i', strtotime($alarm['started_at'])) ?>
                    <?php if ($alarm['acknowledged']): ?>
                    &bull; Acknowledged
                    <?php endif; ?>
                </div>
            </div>
            <?php endforeach; ?>
        </div>
        <?php endif; ?>

        <?php if ($health): ?>
        <!-- System Health Cards -->
        <h3 class="section-title">System Health</h3>
        <div class="data-grid">
            <div class="data-card">
                <div class="data-card-label">CPU Temp</div>
                <div class="data-card-value <?= $health['cpu_temp'] > 70 ? 'danger' : ($health['cpu_temp'] > 60 ? 'warning' : '') ?>">
                    <?= $health['cpu_temp'] ? number_format($health['cpu_temp'], 1) : '--' ?>
                    <span class="data-card-unit">&deg;C</span>
                </div>
            </div>
            <div class="data-card">
                <div class="data-card-label">Memory</div>
                <div class="data-card-value <?= $health['memory_used_pct'] > 85 ? 'danger' : ($health['memory_used_pct'] > 70 ? 'warning' : '') ?>">
                    <?= $health['memory_used_pct'] ? number_format($health['memory_used_pct'], 0) : '--' ?>
                    <span class="data-card-unit">%</span>
                </div>
            </div>
            <div class="data-card">
                <div class="data-card-label">Disk</div>
                <div class="data-card-value <?= $health['disk_used_pct'] > 90 ? 'danger' : ($health['disk_used_pct'] > 80 ? 'warning' : '') ?>">
                    <?= $health['disk_used_pct'] ? number_format($health['disk_used_pct'], 0) : '--' ?>
                    <span class="data-card-unit">%</span>
                </div>
            </div>
            <div class="data-card">
                <div class="data-card-label">Uptime</div>
                <div class="data-card-value">
                    <?= $health['uptime_display'] ?? '--' ?>
                </div>
            </div>
            <div class="data-card">
                <div class="data-card-label">Controllers</div>
                <div class="data-card-value <?= $health['controllers_offline'] > 0 ? 'warning' : 'success' ?>">
                    <?= $health['controllers_online'] ?? 0 ?>
                    <span class="data-card-unit">online</span>
                </div>
            </div>
            <div class="data-card">
                <div class="data-card-label">Active Alarms</div>
                <div class="data-card-value <?= $health['alarms_critical'] > 0 ? 'danger' : ($health['alarms_warning'] > 0 ? 'warning' : 'success') ?>">
                    <?= $health['alarms_total'] ?? 0 ?>
                </div>
            </div>
        </div>

        <?php if (!empty($health['controllers'])): ?>
        <h3 class="section-title">Pool Controllers</h3>
        <div class="controllers-grid">
            <?php foreach ($health['controllers'] as $ctrl): ?>
            <div class="controller-card">
                <div class="controller-status <?= !empty($ctrl['online']) ? 'online' : 'offline' ?>"></div>
                <div class="controller-info">
                    <div class="controller-host"><?= htmlspecialchars($ctrl['host']) ?></div>
                    <div class="controller-time">
                        <?php if (!empty($ctrl['online'])): ?>
                            Online
                        <?php elseif (isset($ctrl['minutes_ago'])): ?>
                            Last reading: <?= $ctrl['minutes_ago'] ?>m ago
                        <?php else: ?>
                            Offline
                        <?php endif; ?>
                    </div>
                </div>
            </div>
            <?php endforeach; ?>
        </div>
        <?php endif; ?>

        <?php if (!empty($health['issues'])): ?>
        <h3 class="section-title">Current Issues</h3>
        <div class="issues-list">
            <?php foreach ($health['issues'] as $issue): ?>
            <div class="issue-item"><?= htmlspecialchars($issue) ?></div>
            <?php endforeach; ?>
        </div>
        <?php endif; ?>

        <?php else: ?>
        <div class="placeholder-message">
            <p>No health data available yet. The device will report data on its next heartbeat.</p>
        </div>
        <?php endif; ?>

        <!-- AI Section -->
        <div class="two-column" style="margin-top: 2rem;">
            <div>
                <h3 class="section-title">AI Suggestions</h3>
                <?php if (!empty($suggestions)): ?>
                    <?php foreach ($suggestions as $s): ?>
                    <div class="suggestion-card">
                        <div class="suggestion-title"><?= htmlspecialchars($s['title']) ?></div>
                        <div class="suggestion-body"><?= htmlspecialchars(substr($s['body'], 0, 150)) ?><?= strlen($s['body']) > 150 ? '...' : '' ?></div>
                        <div class="suggestion-meta">
                            <?= htmlspecialchars($s['suggestion_type'] ?: 'tip') ?> &bull;
                            <?= date('d M', strtotime($s['created_at'])) ?> &bull;
                            <?= htmlspecialchars($s['status']) ?>
                        </div>
                    </div>
                    <?php endforeach; ?>
                <?php else: ?>
                    <div class="placeholder-message">
                        <p>No AI suggestions yet.</p>
                    </div>
                <?php endif; ?>
            </div>

            <div>
                <h3 class="section-title">Recent Q&A</h3>
                <?php if (!empty($responses)): ?>
                    <?php foreach ($responses as $r): ?>
                    <div class="response-card">
                        <div class="response-question"><?= htmlspecialchars($r['question_text']) ?></div>
                        <div class="response-answer"><?= htmlspecialchars($r['answer']) ?></div>
                        <div class="response-meta">
                            <?= htmlspecialchars($r['category'] ?: 'general') ?> &bull;
                            <?= date('d M H:i', strtotime($r['answered_at'])) ?>
                        </div>
                    </div>
                    <?php endforeach; ?>
                <?php else: ?>
                    <div class="placeholder-message">
                        <p>No questions answered yet.</p>
                    </div>
                <?php endif; ?>
            </div>
        </div>

        <!-- Historical Data Placeholder -->
        <h3 class="section-title" style="margin-top: 2rem;">Historical Data</h3>
        <div class="placeholder-message">
            <p>Historical charts coming soon. This will show temperature, memory, and alarm trends over time.</p>
        </div>
    </main>

    <script>
        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
