<?php
/**
 * AI Learnings & Knowledge Base
 * View pool profiles, patterns, and Claude conversation history
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Check if AI tables exist
try {
    $pdo->query("SELECT 1 FROM ai_pool_profiles LIMIT 1");
} catch (PDOException $e) {
    header('Location: ai_settings.php');
    exit;
}

// Get tab
$tab = $_GET['tab'] ?? 'profiles';

// Get pool profiles with device info
$profiles = [];
try {
    $profiles = $pdo->query("
        SELECT p.*, d.name as device_name, d.device_uuid
        FROM ai_pool_profiles p
        JOIN pi_devices d ON p.device_id = d.id
        ORDER BY p.updated_at DESC
    ")->fetchAll(PDO::FETCH_ASSOC);
} catch (PDOException $e) {}

// Get conversation logs
$conversations = [];
if ($tab === 'conversations') {
    try {
        $conversations = $pdo->query("
            SELECT c.*, d.name as device_name
            FROM ai_conversation_log c
            LEFT JOIN pi_devices d ON c.device_id = d.id
            ORDER BY c.created_at DESC
            LIMIT 100
        ")->fetchAll(PDO::FETCH_ASSOC);
    } catch (PDOException $e) {}
}

// Get pool norms (cross-pool patterns)
$norms = [];
if ($tab === 'patterns') {
    try {
        $norms = $pdo->query("
            SELECT * FROM ai_pool_norms ORDER BY pool_type, metric
        ")->fetchAll(PDO::FETCH_ASSOC);
    } catch (PDOException $e) {}
}

// Get summary stats
$stats = [
    'total_profiles' => count($profiles),
    'total_conversations' => 0,
    'total_insights' => 0,
    'avg_maturity' => 0
];

try {
    $stats['total_conversations'] = $pdo->query("SELECT COUNT(*) FROM ai_conversation_log")->fetchColumn();
    $stats['avg_maturity'] = $pdo->query("SELECT ROUND(AVG(maturity_score), 1) FROM ai_pool_profiles")->fetchColumn() ?? 0;
    $stats['total_insights'] = $pdo->query("SELECT COUNT(DISTINCT pool_type) FROM ai_pool_norms")->fetchColumn();
} catch (PDOException $e) {}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Learnings - PoolAIssistant</title>
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
            --purple: #8b5cf6;
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
        header h1 span { color: var(--purple); }

        .nav-links { display: flex; gap: 8px; flex-wrap: wrap; }
        .nav-links a {
            background: var(--surface-2);
            color: var(--text);
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.875rem;
        }
        .nav-links a:hover { background: var(--border); }
        .nav-links a.active { background: var(--purple); }

        .stats-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--surface);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-card .value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--purple);
        }
        .stat-card .label {
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
        }
        .tab {
            padding: 10px 20px;
            background: var(--surface);
            border: none;
            border-radius: 8px;
            color: var(--text);
            cursor: pointer;
            font-size: 0.875rem;
            text-decoration: none;
        }
        .tab:hover { background: var(--surface-2); }
        .tab.active { background: var(--purple); }

        .card {
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 20px;
        }
        .card-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--surface-2);
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .card-body { padding: 20px; }

        .profile-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }

        .profile-card {
            background: var(--surface);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--surface-2);
        }
        .profile-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
        }
        .profile-name {
            font-size: 1.125rem;
            font-weight: 600;
        }
        .profile-pool {
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .maturity-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .maturity-low { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .maturity-medium { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .maturity-high { background: rgba(34, 197, 94, 0.2); color: var(--success); }

        .profile-stats {
            display: flex;
            gap: 16px;
            margin-bottom: 16px;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .profile-stats span { display: flex; align-items: center; gap: 4px; }

        .profile-data {
            background: var(--bg);
            padding: 12px;
            border-radius: 8px;
            font-size: 0.8rem;
            font-family: 'SF Mono', Monaco, monospace;
            max-height: 200px;
            overflow-y: auto;
        }
        .profile-data pre {
            white-space: pre-wrap;
            word-break: break-word;
        }

        .conversation-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .conversation-item {
            background: var(--surface-2);
            padding: 16px;
            border-radius: 8px;
        }
        .conversation-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 0.875rem;
        }
        .conversation-type {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            background: rgba(139, 92, 246, 0.2);
            color: var(--purple);
        }
        .conversation-meta {
            color: var(--text-muted);
            font-size: 0.75rem;
            display: flex;
            gap: 16px;
        }
        .conversation-content {
            font-size: 0.875rem;
            color: var(--text-muted);
        }

        .pattern-table {
            width: 100%;
            border-collapse: collapse;
        }
        .pattern-table th,
        .pattern-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--surface-2);
        }
        .pattern-table th {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-muted);
            font-weight: 600;
        }
        .pattern-table td {
            font-size: 0.875rem;
        }
        .pattern-table tr:last-child td { border-bottom: none; }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }
        .empty-state h3 { margin-bottom: 8px; color: var(--text); }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.875rem;
            cursor: pointer;
            border: none;
            text-decoration: none;
        }
        .btn-sm { padding: 6px 12px; font-size: 0.75rem; }
        .btn-secondary { background: var(--surface-2); color: var(--text); }
        .btn-secondary:hover { background: var(--border); }
        .btn-purple { background: var(--purple); color: white; }

        .expand-btn {
            background: none;
            border: none;
            color: var(--accent);
            cursor: pointer;
            font-size: 0.75rem;
            padding: 4px 8px;
        }

        @media (max-width: 768px) {
            .profile-grid { grid-template-columns: 1fr; }
            .nav-links { overflow-x: auto; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><span>AI</span> Learnings</h1>
            <nav class="nav-links">
                <a href="ai_dashboard.php">Dashboard</a>
                <a href="ai_questions.php">Questions</a>
                <a href="ai_responses.php">Responses</a>
                <a href="ai_suggestions.php">Suggestions</a>
                <a href="ai_learnings.php" class="active">Learnings</a>
                <a href="ai_settings.php">Settings</a>
                <a href="index.php">Devices</a>
            </nav>
        </header>

        <div class="stats-bar">
            <div class="stat-card">
                <div class="value"><?= $stats['total_profiles'] ?></div>
                <div class="label">Pool Profiles</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= number_format($stats['total_conversations']) ?></div>
                <div class="label">Claude Conversations</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['avg_maturity'] ?>%</div>
                <div class="label">Avg Profile Maturity</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['total_insights'] ?></div>
                <div class="label">Pool Type Patterns</div>
            </div>
        </div>

        <div class="tabs">
            <a href="?tab=profiles" class="tab <?= $tab === 'profiles' ? 'active' : '' ?>">Pool Profiles</a>
            <a href="?tab=conversations" class="tab <?= $tab === 'conversations' ? 'active' : '' ?>">Conversation Log</a>
            <a href="?tab=patterns" class="tab <?= $tab === 'patterns' ? 'active' : '' ?>">Cross-Pool Patterns</a>
        </div>

        <?php if ($tab === 'profiles'): ?>
            <?php if (empty($profiles)): ?>
                <div class="empty-state">
                    <h3>No Pool Profiles Yet</h3>
                    <p>Claude will build knowledge profiles as operators answer questions about their pools.</p>
                </div>
            <?php else: ?>
                <div class="profile-grid">
                    <?php foreach ($profiles as $profile): ?>
                        <?php
                        $maturity = $profile['maturity_score'] ?? 0;
                        $maturity_class = $maturity < 30 ? 'low' : ($maturity < 70 ? 'medium' : 'high');
                        $profile_data = json_decode($profile['profile_json'] ?? '{}', true);
                        $patterns_data = json_decode($profile['patterns_json'] ?? '{}', true);
                        ?>
                        <div class="profile-card">
                            <div class="profile-header">
                                <div>
                                    <div class="profile-name"><?= htmlspecialchars($profile['device_name'] ?: 'Unknown Device') ?></div>
                                    <div class="profile-pool"><?= htmlspecialchars($profile['pool'] ?: 'Default Pool') ?></div>
                                </div>
                                <span class="maturity-badge maturity-<?= $maturity_class ?>"><?= $maturity ?>% Complete</span>
                            </div>

                            <div class="profile-stats">
                                <span><?= $profile['questions_answered'] ?? 0 ?> answers</span>
                                <span>Updated <?= $profile['updated_at'] ? date('M j', strtotime($profile['updated_at'])) : 'Never' ?></span>
                            </div>

                            <?php if (!empty($profile_data)): ?>
                                <div class="profile-data">
                                    <pre><?= htmlspecialchars(json_encode($profile_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)) ?></pre>
                                </div>
                            <?php else: ?>
                                <div style="color: var(--text-muted); font-size: 0.875rem; font-style: italic;">
                                    No profile data collected yet
                                </div>
                            <?php endif; ?>
                        </div>
                    <?php endforeach; ?>
                </div>
            <?php endif; ?>

        <?php elseif ($tab === 'conversations'): ?>
            <?php if (empty($conversations)): ?>
                <div class="empty-state">
                    <h3>No Conversations Yet</h3>
                    <p>Claude API interactions will appear here once the system starts analyzing responses.</p>
                </div>
            <?php else: ?>
                <div class="card">
                    <div class="card-header">
                        Recent Claude Interactions
                        <a href="ai_settings.php" class="btn btn-sm btn-secondary">Download Backup</a>
                    </div>
                    <div class="card-body">
                        <div class="conversation-list">
                            <?php foreach ($conversations as $conv): ?>
                                <div class="conversation-item">
                                    <div class="conversation-header">
                                        <span class="conversation-type"><?= htmlspecialchars($conv['action_type'] ?? 'unknown') ?></span>
                                        <span style="color: var(--text-muted);">
                                            <?= $conv['device_name'] ? htmlspecialchars($conv['device_name']) : 'System' ?>
                                        </span>
                                    </div>
                                    <div class="conversation-content">
                                        <?php if ($conv['prompt_summary']): ?>
                                            <strong>Prompt:</strong> <?= htmlspecialchars(substr($conv['prompt_summary'], 0, 200)) ?>...
                                        <?php endif; ?>
                                        <?php if ($conv['response_summary']): ?>
                                            <br><strong>Response:</strong> <?= htmlspecialchars(substr($conv['response_summary'], 0, 200)) ?>...
                                        <?php endif; ?>
                                    </div>
                                    <div class="conversation-meta">
                                        <span><?= date('M j, g:ia', strtotime($conv['created_at'])) ?></span>
                                        <span><?= number_format($conv['tokens_used'] ?? 0) ?> tokens</span>
                                        <span><?= ($conv['duration_ms'] ?? 0) ?>ms</span>
                                        <span style="color: <?= $conv['success'] ? 'var(--success)' : 'var(--danger)' ?>;">
                                            <?= $conv['success'] ? 'Success' : 'Failed' ?>
                                        </span>
                                    </div>
                                </div>
                            <?php endforeach; ?>
                        </div>
                    </div>
                </div>
            <?php endif; ?>

        <?php elseif ($tab === 'patterns'): ?>
            <?php if (empty($norms)): ?>
                <div class="empty-state">
                    <h3>No Patterns Detected Yet</h3>
                    <p>As Claude analyzes data across multiple pools, patterns and norms will be identified here.</p>
                </div>
            <?php else: ?>
                <div class="card">
                    <div class="card-header">Cross-Pool Norms & Patterns</div>
                    <div class="card-body">
                        <table class="pattern-table">
                            <thead>
                                <tr>
                                    <th>Pool Type</th>
                                    <th>Metric</th>
                                    <th>Average</th>
                                    <th>Range</th>
                                    <th>Sample Size</th>
                                    <th>Last Updated</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($norms as $norm): ?>
                                    <tr>
                                        <td><?= htmlspecialchars($norm['pool_type']) ?></td>
                                        <td><?= htmlspecialchars($norm['metric']) ?></td>
                                        <td><strong><?= number_format($norm['value'], 2) ?></strong></td>
                                        <td>
                                            <?= number_format($norm['min_value'] ?? 0, 2) ?> -
                                            <?= number_format($norm['max_value'] ?? 0, 2) ?>
                                        </td>
                                        <td><?= number_format($norm['sample_count'] ?? 0) ?></td>
                                        <td><?= date('M j, Y', strtotime($norm['updated_at'])) ?></td>
                                    </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                    </div>
                </div>
            <?php endif; ?>
        <?php endif; ?>
    </div>
</body>
</html>
