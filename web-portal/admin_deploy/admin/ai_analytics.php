<?php
/**
 * AI Analytics Dashboard - Cross-Pool Insights
 */
require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Get all devices with their profiles
$devices = $pdo->query("
    SELECT
        d.id,
        d.name,
        d.device_uuid,
        d.last_seen,
        p.profile_json,
        p.maturity_score,
        p.questions_answered,
        h.controllers_online,
        h.controllers_offline,
        h.alarms_total,
        h.alarms_critical,
        h.cpu_temp,
        h.memory_used_pct,
        h.disk_used_pct
    FROM pi_devices d
    LEFT JOIN ai_pool_profiles p ON p.device_id = d.id
    LEFT JOIN (
        SELECT device_id, controllers_online, controllers_offline, alarms_total,
               alarms_critical, cpu_temp, memory_used_pct, disk_used_pct
        FROM device_health h1
        WHERE ts = (SELECT MAX(ts) FROM device_health h2 WHERE h2.device_id = h1.device_id)
    ) h ON h.device_id = d.id
    WHERE d.is_active = 1
    ORDER BY d.last_seen DESC
")->fetchAll(PDO::FETCH_ASSOC);

// Aggregate stats
$totalDevices = count($devices);
$onlineDevices = 0;
$totalAlarms = 0;
$criticalAlarms = 0;
$avgTemp = [];
$avgMemory = [];
$avgDisk = [];

foreach ($devices as $d) {
    if ($d['last_seen'] && strtotime($d['last_seen']) > strtotime('-20 minutes')) {
        $onlineDevices++;
    }
    $totalAlarms += (int)($d['alarms_total'] ?? 0);
    $criticalAlarms += (int)($d['alarms_critical'] ?? 0);
    if ($d['cpu_temp']) $avgTemp[] = $d['cpu_temp'];
    if ($d['memory_used_pct']) $avgMemory[] = $d['memory_used_pct'];
    if ($d['disk_used_pct']) $avgDisk[] = $d['disk_used_pct'];
}

// Get pool type distribution from profiles
$poolTypes = [];
foreach ($devices as $d) {
    if ($d['profile_json']) {
        $profile = json_decode($d['profile_json'], true);
        $type = $profile['pool_type'] ?? 'Unknown';
        $poolTypes[$type] = ($poolTypes[$type] ?? 0) + 1;
    }
}

// Get response stats
$responseStats = $pdo->query("
    SELECT
        DATE(answered_at) as date,
        COUNT(*) as count
    FROM ai_responses
    WHERE answered_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
    GROUP BY DATE(answered_at)
    ORDER BY date ASC
")->fetchAll(PDO::FETCH_ASSOC);

// Get suggestion stats
$suggestionStats = $pdo->query("
    SELECT
        status,
        COUNT(*) as count
    FROM ai_suggestions
    GROUP BY status
")->fetchAll(PDO::FETCH_ASSOC);

// Get most common answers per question
$topAnswers = $pdo->query("
    SELECT
        q.text as question,
        q.category,
        r.answer,
        COUNT(*) as count
    FROM ai_responses r
    JOIN ai_questions q ON r.question_id = q.id
    GROUP BY q.id, r.answer
    ORDER BY count DESC
    LIMIT 20
")->fetchAll(PDO::FETCH_ASSOC);

// Get norms if they exist
$norms = $pdo->query("
    SELECT pool_type, metric, value, sample_count
    FROM ai_pool_norms
    ORDER BY pool_type, metric
")->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Analytics - PoolAIssistant Admin</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-2: #334155;
            --accent: #3b82f6;
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
            padding: 20px;
            line-height: 1.5;
        }
        h1 { margin-bottom: 0.5rem; }
        .subtitle { color: var(--text-muted); margin-bottom: 2rem; }
        .nav-links { margin-bottom: 2rem; }
        .nav-links a {
            color: var(--accent);
            text-decoration: none;
            margin-right: 1rem;
        }
        .nav-links a:hover { text-decoration: underline; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: var(--surface);
            border-radius: 12px;
            padding: 1.5rem;
        }
        .stat-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
        }
        .stat-value.success { color: var(--success); }
        .stat-value.warning { color: var(--warning); }
        .stat-value.danger { color: var(--danger); }
        .section {
            background: var(--surface);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .section-title {
            font-size: 1.25rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th { color: var(--text-muted); font-weight: 500; font-size: 0.875rem; }
        .badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }
        .badge-success { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge-warning { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge-danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .two-col {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
        }
        @media (max-width: 900px) {
            .two-col { grid-template-columns: 1fr; }
        }
        .progress-bar {
            height: 8px;
            background: var(--surface-2);
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: var(--accent);
            transition: width 0.3s;
        }
        .chart-placeholder {
            background: var(--surface-2);
            border-radius: 8px;
            padding: 3rem;
            text-align: center;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <h1>AI Analytics</h1>
    <p class="subtitle">Cross-pool insights and learning patterns</p>

    <div class="nav-links">
        <a href="index.php">&larr; Admin Home</a>
        <a href="ai_dashboard.php">AI Dashboard</a>
        <a href="ai_questions.php">Questions</a>
        <a href="ai_responses.php">Responses</a>
        <a href="ai_suggestions.php">Suggestions</a>
    </div>

    <!-- Overview Stats -->
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">Total Devices</div>
            <div class="stat-value"><?= $totalDevices ?></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Online Now</div>
            <div class="stat-value success"><?= $onlineDevices ?></div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Total Alarms</div>
            <div class="stat-value <?= $criticalAlarms > 0 ? 'danger' : ($totalAlarms > 0 ? 'warning' : 'success') ?>">
                <?= $totalAlarms ?>
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Avg CPU Temp</div>
            <div class="stat-value">
                <?= count($avgTemp) ? number_format(array_sum($avgTemp) / count($avgTemp), 1) : '--' ?>&deg;C
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Avg Memory</div>
            <div class="stat-value">
                <?= count($avgMemory) ? number_format(array_sum($avgMemory) / count($avgMemory), 0) : '--' ?>%
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Avg Disk</div>
            <div class="stat-value">
                <?= count($avgDisk) ? number_format(array_sum($avgDisk) / count($avgDisk), 0) : '--' ?>%
            </div>
        </div>
    </div>

    <div class="two-col">
        <!-- Pool Type Distribution -->
        <div class="section">
            <h2 class="section-title">Pool Type Distribution</h2>
            <?php if (!empty($poolTypes)): ?>
                <?php foreach ($poolTypes as $type => $count): ?>
                <div style="margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                        <span><?= htmlspecialchars($type) ?></span>
                        <span><?= $count ?> device<?= $count > 1 ? 's' : '' ?></span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: <?= ($count / $totalDevices) * 100 ?>%"></div>
                    </div>
                </div>
                <?php endforeach; ?>
            <?php else: ?>
                <p style="color: var(--text-muted)">No pool profiles created yet. Profiles are built from AI question responses.</p>
            <?php endif; ?>
        </div>

        <!-- Suggestion Status -->
        <div class="section">
            <h2 class="section-title">Suggestion Status</h2>
            <?php if (!empty($suggestionStats)): ?>
                <table>
                    <tr><th>Status</th><th>Count</th></tr>
                    <?php foreach ($suggestionStats as $stat): ?>
                    <tr>
                        <td>
                            <span class="badge badge-<?= $stat['status'] === 'acted_upon' ? 'success' : ($stat['status'] === 'dismissed' ? 'warning' : 'info') ?>">
                                <?= htmlspecialchars($stat['status']) ?>
                            </span>
                        </td>
                        <td><?= $stat['count'] ?></td>
                    </tr>
                    <?php endforeach; ?>
                </table>
            <?php else: ?>
                <p style="color: var(--text-muted)">No suggestions generated yet.</p>
            <?php endif; ?>
        </div>
    </div>

    <!-- Common Answers -->
    <div class="section">
        <h2 class="section-title">Common Answers Across All Pools</h2>
        <?php if (!empty($topAnswers)): ?>
        <table>
            <tr>
                <th>Question</th>
                <th>Category</th>
                <th>Answer</th>
                <th>Count</th>
            </tr>
            <?php foreach ($topAnswers as $row): ?>
            <tr>
                <td><?= htmlspecialchars(substr($row['question'], 0, 60)) ?><?= strlen($row['question']) > 60 ? '...' : '' ?></td>
                <td><span class="badge"><?= htmlspecialchars($row['category'] ?: 'general') ?></span></td>
                <td><?= htmlspecialchars($row['answer']) ?></td>
                <td><?= $row['count'] ?></td>
            </tr>
            <?php endforeach; ?>
        </table>
        <?php else: ?>
            <p style="color: var(--text-muted)">No responses collected yet.</p>
        <?php endif; ?>
    </div>

    <!-- Device Comparison -->
    <div class="section">
        <h2 class="section-title">Device Comparison</h2>
        <table>
            <tr>
                <th>Device</th>
                <th>Status</th>
                <th>Controllers</th>
                <th>Alarms</th>
                <th>CPU</th>
                <th>Memory</th>
                <th>Q&A Score</th>
            </tr>
            <?php foreach ($devices as $d): ?>
            <tr>
                <td><?= htmlspecialchars($d['name']) ?></td>
                <td>
                    <?php
                    $online = $d['last_seen'] && strtotime($d['last_seen']) > strtotime('-20 minutes');
                    ?>
                    <span class="badge badge-<?= $online ? 'success' : 'danger' ?>">
                        <?= $online ? 'Online' : 'Offline' ?>
                    </span>
                </td>
                <td><?= ($d['controllers_online'] ?? 0) ?>/<?= (($d['controllers_online'] ?? 0) + ($d['controllers_offline'] ?? 0)) ?></td>
                <td>
                    <?php if (($d['alarms_critical'] ?? 0) > 0): ?>
                        <span class="badge badge-danger"><?= $d['alarms_critical'] ?> critical</span>
                    <?php elseif (($d['alarms_total'] ?? 0) > 0): ?>
                        <span class="badge badge-warning"><?= $d['alarms_total'] ?></span>
                    <?php else: ?>
                        <span class="badge badge-success">0</span>
                    <?php endif; ?>
                </td>
                <td><?= $d['cpu_temp'] ? number_format($d['cpu_temp'], 1) . '&deg;C' : '--' ?></td>
                <td><?= $d['memory_used_pct'] ? number_format($d['memory_used_pct'], 0) . '%' : '--' ?></td>
                <td><?= $d['questions_answered'] ?? 0 ?></td>
            </tr>
            <?php endforeach; ?>
        </table>
    </div>

    <!-- Response Trends -->
    <div class="section">
        <h2 class="section-title">Response Activity (Last 30 Days)</h2>
        <div class="chart-placeholder">
            <p>Response trend chart coming soon.</p>
            <p style="font-size: 0.875rem; margin-top: 0.5rem;">
                Total responses: <?= array_sum(array_column($responseStats, 'count')) ?>
            </p>
        </div>
    </div>
</body>
</html>
