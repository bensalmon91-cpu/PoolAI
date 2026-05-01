<?php
/**
 * PoolAIssistant Portal - Device Detail View
 */

require_once __DIR__ . '/includes/PortalAuth.php';
require_once __DIR__ . '/includes/PortalDevices.php';
require_once __DIR__ . '/includes/ai_disclaimer.php';

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
$readings = $devicesManager->getLatestReadings($device['device_id']);
$suggestions = $devicesManager->getAISuggestions($device['device_id'], 5);
$responses = $devicesManager->getAIResponses($device['device_id'], 5);

/** Color-class helper for pool chemistry thresholds (CLAUDE.md). */
function chem_class(string $metric, ?float $v): string {
    if ($v === null) return '';
    switch ($metric) {
        case 'pH':
            if ($v < 7.0 || $v > 7.8) return 'danger';
            if ($v < 7.2 || $v > 7.6) return 'warning';
            return 'success';
        case 'Chlorine':
            if ($v < 0.5 || $v > 4.0) return 'danger';
            if ($v < 1.0 || $v > 3.0) return 'warning';
            return 'success';
        case 'ORP':
            if ($v < 600 || $v > 800) return 'danger';
            if ($v < 650 || $v > 750) return 'warning';
            return 'success';
        default:
            return '';
    }
}

/** "X min ago" relative-time, returns null if no timestamp. */
function ago_label(?string $ts): ?string {
    if (!$ts) return null;
    $secs = max(0, time() - strtotime($ts));
    if ($secs < 60) return 'just now';
    if ($secs < 3600) return floor($secs / 60) . 'm ago';
    if ($secs < 86400) return floor($secs / 3600) . 'h ago';
    return floor($secs / 86400) . 'd ago';
}

$csrfToken = $auth->generateCSRFToken();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title><?= htmlspecialchars($device['nickname'] ?: $device['alias'] ?: 'Device') ?> - PoolAIssistant</title>

    <!-- PWA Meta Tags -->
    <meta name="theme-color" content="#0066cc">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">

    <link rel="stylesheet" href="assets/css/portal.css">
    <script src="/assets/js/pwa.js" defer></script>
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
        .ai-disclaimer {
            background: #fff7ed;
            border: 1px solid #fdba74;
            border-left: 4px solid #f97316;
            color: #7c2d12;
            padding: 0.75rem 1rem;
            margin-bottom: 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            line-height: 1.45;
        }
        .ai-disclaimer strong { color: #7c2d12; }
        .ai-disclaimer--strong {
            background: #fef2f2;
            border-color: #fca5a5;
            border-left-color: #dc2626;
            color: #7f1d1d;
        }
        .ai-disclaimer__hsg {
            margin-top: 0.4rem;
            font-size: 0.8rem;
            font-style: italic;
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

        <!-- Pool Chemistry Cards (latest from device_readings_latest) -->
        <h3 class="section-title">Pool Chemistry</h3>
        <?php
            $chem = [
                ['key' => 'pH',       'label' => 'pH',       'unit' => '',    'fmt' => '%.2f'],
                ['key' => 'Chlorine', 'label' => 'Chlorine', 'unit' => 'ppm', 'fmt' => '%.2f'],
                ['key' => 'ORP',      'label' => 'ORP',      'unit' => 'mV',  'fmt' => '%.0f'],
                ['key' => 'Temp',     'label' => 'Temp',     'unit' => '°C',  'fmt' => '%.1f'],
            ];
            $latestTs = null;
            foreach ($chem as $c) {
                $r = $readings[$c['key']] ?? null;
                if ($r && (!$latestTs || strcmp($r['received_at'], $latestTs) > 0)) {
                    $latestTs = $r['received_at'];
                }
            }
        ?>
        <div class="data-grid">
            <?php foreach ($chem as $c):
                $r   = $readings[$c['key']] ?? null;
                $val = $r['value'] ?? null;
                $cls = chem_class($c['key'], $val);
                $unit = $r['unit'] ?: $c['unit'];
            ?>
            <div class="data-card">
                <div class="data-card-label"><?= htmlspecialchars($c['label']) ?></div>
                <div class="data-card-value <?= $cls ?>">
                    <?= $val === null ? '—' : sprintf($c['fmt'], $val) ?>
                    <?php if ($val !== null && $unit !== ''): ?>
                        <span class="data-card-unit"><?= htmlspecialchars($unit) ?></span>
                    <?php endif; ?>
                </div>
            </div>
            <?php endforeach; ?>
        </div>
        <?php if ($latestTs): ?>
            <p class="device-meta" style="margin-top:-1rem; margin-bottom:2rem;">
                Last reading <?= htmlspecialchars(ago_label($latestTs)) ?>
            </p>
        <?php else: ?>
            <p class="device-meta" style="margin-top:-1rem; margin-bottom:2rem;">
                Waiting for first chemistry snapshot from this Pi.
            </p>
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
                <?php render_ai_disclaimer(); ?>
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
