<?php
/**
 * PoolAIssistant Admin Panel
 * Device management and monitoring dashboard
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

// Require admin login
requireAdmin();

$pdo = db();

// Get all devices with latest health
$stmt = $pdo->query("
    SELECT
        d.id,
        d.device_uuid,
        d.name,
        d.api_key,
        d.is_active,
        d.last_seen,
        d.created_at,
        h.software_version,
        h.ip_address,
        h.uptime_seconds,
        h.disk_used_pct,
        h.memory_used_pct,
        h.cpu_temp,
        h.controllers_online,
        h.controllers_offline,
        h.alarms_total,
        h.alarms_critical,
        h.has_issues,
        h.issues_json,
        h.ts as health_ts
    FROM pi_devices d
    LEFT JOIN (
        SELECT h1.*
        FROM device_health h1
        INNER JOIN (
            SELECT device_id, MAX(ts) as max_ts
            FROM device_health
            GROUP BY device_id
        ) h2 ON h1.device_id = h2.device_id AND h1.ts = h2.max_ts
    ) h ON d.id = h.device_id
    WHERE d.is_active = 1
    ORDER BY d.name, d.id
");
$devices = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Calculate online status
$now = time();
foreach ($devices as &$device) {
    $last_seen = $device['last_seen'] ? strtotime($device['last_seen']) : null;
    $minutes_ago = $last_seen ? round(($now - $last_seen) / 60) : null;
    $device['is_online'] = $minutes_ago !== null && $minutes_ago < 20;
    $device['minutes_ago'] = $minutes_ago;
}
unset($device);

// Get software updates
$stmt = $pdo->query("SELECT * FROM software_updates WHERE is_active = 1 ORDER BY created_at DESC LIMIT 10");
$updates = $stmt->fetchAll(PDO::FETCH_ASSOC);

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PoolAIssistant Admin</title>
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
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }
        header h1 { font-size: 1.5rem; font-weight: 600; }
        header h1 span { color: var(--accent); }
        .logout-btn {
            background: var(--surface-2);
            color: var(--text);
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.875rem;
        }
        .logout-btn:hover { background: var(--border); }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--surface);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-card .value { font-size: 2rem; font-weight: 700; color: var(--accent); }
        .stat-card .label { font-size: 0.875rem; color: var(--text-muted); margin-top: 4px; }

        .section { margin-bottom: 40px; }
        .section h2 {
            font-size: 1.25rem;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section h2::before { content: ''; width: 4px; height: 24px; background: var(--accent); border-radius: 2px; }

        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
        }
        th, td { padding: 12px 16px; text-align: left; }
        th { background: var(--surface-2); font-weight: 600; font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
        tr:not(:last-child) td { border-bottom: 1px solid var(--surface-2); }
        tr:hover td { background: rgba(59, 130, 246, 0.05); }

        .status-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-dot.online { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .status-dot.offline { background: var(--danger); }
        .status-dot.warning { background: var(--warning); }

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

        .mono { font-family: 'SF Mono', Monaco, monospace; font-size: 0.875rem; color: var(--text-muted); }
        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.875rem; }

        .btn {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.875rem;
            cursor: pointer;
            border: none;
            text-decoration: none;
            transition: all 0.15s;
        }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-secondary { background: var(--surface-2); color: var(--text); }
        .btn-secondary:hover { background: var(--border); }
        .btn-sm { padding: 4px 8px; font-size: 0.75rem; }

        .editable-alias {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: inherit;
            width: 100%;
            max-width: 200px;
        }
        .editable-alias:hover { border-color: var(--border); }
        .editable-alias:focus {
            outline: none;
            border-color: var(--accent);
            background: var(--surface-2);
        }
        .alias-saved {
            color: var(--success);
            font-size: 0.75rem;
            margin-left: 8px;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .alias-saved.show { opacity: 1; }

        .actions { display: flex; gap: 8px; }

        .badge.clickable { cursor: pointer; }
        .badge.clickable:hover { filter: brightness(1.2); }

        /* Modal styles */
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
            max-width: 500px;
            width: 90%;
            max-height: 80vh;
            overflow: auto;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid var(--surface-2);
        }
        .modal-header h3 { font-size: 1.125rem; font-weight: 600; }
        .modal-close {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }
        .modal-close:hover { color: var(--text); }
        .modal-body { padding: 20px; }
        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            padding: 16px 20px;
            border-top: 1px solid var(--surface-2);
        }
        .issue-item {
            background: var(--surface-2);
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 12px;
        }
        .issue-item:last-child { margin-bottom: 0; }
        .issue-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
        .issue-value { font-weight: 500; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-danger:hover { background: #dc2626; }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }
        .empty-state h3 { margin-bottom: 8px; }

        @media (max-width: 768px) {
            .container { padding: 12px; }
            table { font-size: 0.875rem; }
            th, td { padding: 8px 12px; }
            .hide-mobile { display: none; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Pool<span>AI</span>ssistant Admin</h1>
            <nav style="display: flex; gap: 8px;">
                <a href="ai_dashboard.php" class="logout-btn" style="background: #8b5cf6;">AI Assistant</a>
                <a href="logout.php" class="logout-btn">Logout</a>
            </nav>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="value"><?= count($devices) ?></div>
                <div class="label">Total Devices</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= count(array_filter($devices, fn($d) => $d['is_online'])) ?></div>
                <div class="label">Online</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= count(array_filter($devices, fn($d) => !$d['is_online'])) ?></div>
                <div class="label">Offline</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= count(array_filter($devices, fn($d) => $d['has_issues'])) ?></div>
                <div class="label">With Issues</div>
            </div>
        </div>

        <div class="section">
            <h2>Devices</h2>
            <?php if (empty($devices)): ?>
                <div class="empty-state">
                    <h3>No devices registered</h3>
                    <p>Devices will appear here once they connect to the server.</p>
                </div>
            <?php else: ?>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Name / Alias</th>
                            <th>Device ID</th>
                            <th class="hide-mobile">Version</th>
                            <th class="hide-mobile">IP Address</th>
                            <th class="hide-mobile">Last Seen</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($devices as $device): ?>
                        <tr data-device-id="<?= $device['id'] ?>">
                            <td>
                                <?php if ($device['is_online']): ?>
                                    <span class="status-dot online"></span>
                                    <?php if ($device['has_issues']): ?>
                                        <span class="badge warning clickable"
                                              onclick="showIssues(<?= $device['id'] ?>, '<?= htmlspecialchars($device['name'] ?: 'Device ' . $device['id'], ENT_QUOTES) ?>', <?= htmlspecialchars(json_encode([
                                                  'issues_json' => $device['issues_json'],
                                                  'alarms_critical' => $device['alarms_critical'],
                                                  'alarms_total' => $device['alarms_total'],
                                                  'controllers_offline' => $device['controllers_offline']
                                              ]), ENT_QUOTES) ?>)">Issues</span>
                                    <?php else: ?>
                                        <span class="badge success">Online</span>
                                    <?php endif; ?>
                                <?php else: ?>
                                    <span class="status-dot offline"></span>
                                    <span class="badge danger">Offline</span>
                                <?php endif; ?>
                            </td>
                            <td>
                                <input type="text"
                                       class="editable-alias"
                                       value="<?= htmlspecialchars($device['name'] ?: 'Device ' . $device['id']) ?>"
                                       data-device-id="<?= $device['id'] ?>"
                                       data-original="<?= htmlspecialchars($device['name'] ?: '') ?>"
                                       placeholder="Enter name..."
                                       onchange="saveAlias(this)"
                                       onkeydown="if(event.key==='Enter')this.blur()">
                                <span class="alias-saved" id="saved-<?= $device['id'] ?>">Saved!</span>
                            </td>
                            <td class="mono"><?= htmlspecialchars(substr($device['device_uuid'] ?? '', 0, 8)) ?>...</td>
                            <td class="hide-mobile"><?= htmlspecialchars($device['software_version'] ?? '-') ?></td>
                            <td class="hide-mobile mono"><?= htmlspecialchars($device['ip_address'] ?? '-') ?></td>
                            <td class="hide-mobile text-muted text-sm">
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
                            </td>
                            <td class="actions">
                                <button class="btn btn-primary btn-sm" onclick="queueTestQuestion(<?= $device['id'] ?>)">Test AI</button>
                                <button class="btn btn-secondary btn-sm" onclick="requestUpload(<?= $device['id'] ?>)">Upload</button>
                                <button class="btn btn-sm" style="background: transparent; color: var(--text-muted); padding: 4px 6px;" onclick="deleteDevice(<?= $device['id'] ?>, '<?= htmlspecialchars($device['name'] ?: 'Device ' . $device['id'], ENT_QUOTES) ?>')" title="Delete device">&times;</button>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            <?php endif; ?>
        </div>

        <div class="section">
            <h2>Software Updates</h2>
            <?php if (empty($updates)): ?>
                <div class="empty-state">
                    <h3>No updates available</h3>
                </div>
            <?php else: ?>
                <table>
                    <thead>
                        <tr>
                            <th>Version</th>
                            <th>Filename</th>
                            <th>Size</th>
                            <th>Description</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($updates as $update): ?>
                        <tr>
                            <td><strong><?= htmlspecialchars($update['version']) ?></strong></td>
                            <td class="mono"><?= htmlspecialchars($update['filename']) ?></td>
                            <td class="text-muted"><?= round($update['file_size'] / 1024 / 1024, 1) ?> MB</td>
                            <td class="text-sm"><?= htmlspecialchars(substr($update['description'] ?? '', 0, 60)) ?><?= strlen($update['description'] ?? '') > 60 ? '...' : '' ?></td>
                            <td class="text-muted text-sm"><?= date('M j, Y', strtotime($update['created_at'])) ?></td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            <?php endif; ?>
        </div>
    </div>

    <!-- Issues Modal -->
    <div class="modal-overlay" id="issuesModal" onclick="if(event.target===this)closeIssuesModal()">
        <div class="modal">
            <div class="modal-header">
                <h3 id="issuesModalTitle">Device Issues</h3>
                <button class="modal-close" onclick="closeIssuesModal()">&times;</button>
            </div>
            <div class="modal-body" id="issuesModalBody">
                <!-- Populated by JS -->
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeIssuesModal()">Close</button>
                <button class="btn btn-danger" id="clearIssuesBtn" onclick="clearIssues()">Clear Issues</button>
            </div>
        </div>
    </div>

    <script>
    let currentIssueDeviceId = null;

    function showIssues(deviceId, deviceName, data) {
        currentIssueDeviceId = deviceId;
        document.getElementById('issuesModalTitle').textContent = deviceName + ' - Issues';

        let html = '';

        // Parse issues_json if present
        if (data.issues_json) {
            try {
                const issues = JSON.parse(data.issues_json);
                if (Array.isArray(issues)) {
                    issues.forEach(issue => {
                        html += `<div class="issue-item">
                            <div class="issue-label">Issue</div>
                            <div class="issue-value">${escapeHtml(typeof issue === 'string' ? issue : JSON.stringify(issue))}</div>
                        </div>`;
                    });
                } else if (typeof issues === 'object') {
                    for (const [key, value] of Object.entries(issues)) {
                        html += `<div class="issue-item">
                            <div class="issue-label">${escapeHtml(key)}</div>
                            <div class="issue-value">${escapeHtml(String(value))}</div>
                        </div>`;
                    }
                }
            } catch (e) {
                html += `<div class="issue-item">
                    <div class="issue-label">Raw Issues</div>
                    <div class="issue-value">${escapeHtml(data.issues_json)}</div>
                </div>`;
            }
        }

        // Show alarm info
        if (data.alarms_critical > 0) {
            html += `<div class="issue-item">
                <div class="issue-label">Critical Alarms</div>
                <div class="issue-value" style="color: var(--danger);">${data.alarms_critical} critical alarm${data.alarms_critical > 1 ? 's' : ''}</div>
            </div>`;
        }

        if (data.alarms_total > 0 && data.alarms_total !== data.alarms_critical) {
            html += `<div class="issue-item">
                <div class="issue-label">Total Alarms</div>
                <div class="issue-value">${data.alarms_total} alarm${data.alarms_total > 1 ? 's' : ''}</div>
            </div>`;
        }

        if (data.controllers_offline > 0) {
            html += `<div class="issue-item">
                <div class="issue-label">Controllers Offline</div>
                <div class="issue-value" style="color: var(--warning);">${data.controllers_offline} controller${data.controllers_offline > 1 ? 's' : ''} offline</div>
            </div>`;
        }

        if (!html) {
            html = '<p class="text-muted">No detailed issue information available.</p>';
        }

        document.getElementById('issuesModalBody').innerHTML = html;
        document.getElementById('issuesModal').classList.add('show');
    }

    function closeIssuesModal() {
        document.getElementById('issuesModal').classList.remove('show');
        currentIssueDeviceId = null;
    }

    function clearIssues() {
        if (!currentIssueDeviceId) return;
        if (!confirm('Clear issues for this device? This will mark the device as healthy until the next heartbeat.')) return;

        const btn = document.getElementById('clearIssuesBtn');
        btn.disabled = true;
        btn.textContent = 'Clearing...';

        fetch('/api/clear_device_issues.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: currentIssueDeviceId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                closeIssuesModal();
                location.reload();
            } else {
                alert('Failed to clear issues: ' + (data.error || 'Unknown error'));
                btn.disabled = false;
                btn.textContent = 'Clear Issues';
            }
        })
        .catch(err => {
            alert('Network error');
            btn.disabled = false;
            btn.textContent = 'Clear Issues';
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function saveAlias(input) {
        const deviceId = input.dataset.deviceId;
        const alias = input.value.trim();
        const savedEl = document.getElementById('saved-' + deviceId);

        fetch('/api/device_alias.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, alias: alias })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                savedEl.classList.add('show');
                setTimeout(() => savedEl.classList.remove('show'), 2000);
                input.dataset.original = alias;
            } else {
                alert('Failed to save: ' + (data.error || 'Unknown error'));
                input.value = input.dataset.original;
            }
        })
        .catch(err => {
            alert('Network error');
            input.value = input.dataset.original;
        });
    }

    function deleteDevice(deviceId, deviceName) {
        if (!confirm('Delete "' + deviceName + '"?\n\nThis will remove the device from the portal. If the device is still running, it will re-register on its next heartbeat.')) return;

        fetch('/api/delete_device.php', {
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
            }
        })
        .catch(err => alert('Network error'));
    }

    function queueTestQuestion(deviceId) {
        fetch('/api/queue_test_question.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                alert('Test question queued!\n\nDevice: ' + data.device_name + '\nQuestion: ' + data.question + '\n\nThe device will receive this on its next heartbeat.');
            } else {
                alert('Failed: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(err => alert('Network error'));
    }

    function requestUpload(deviceId) {
        if (!confirm('Request data upload from this device?')) return;

        fetch('/api/admin_request_upload.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                alert('Upload requested. Device will upload on next heartbeat.');
            } else {
                alert('Failed: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(err => alert('Network error'));
    }

    // Auto-refresh every 60 seconds
    setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
