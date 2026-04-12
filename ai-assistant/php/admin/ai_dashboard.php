<?php
/**
 * AI Assistant Dashboard
 * Overview of AI system activity and metrics
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Get overview stats
$stats = [];

// Total questions
$stats['questions'] = $pdo->query("SELECT COUNT(*) FROM ai_questions WHERE is_active = 1")->fetchColumn();

// Total responses
$stats['responses'] = $pdo->query("SELECT COUNT(*) FROM ai_responses")->fetchColumn();

// Responses this week
$stats['responses_week'] = $pdo->query("
    SELECT COUNT(*) FROM ai_responses WHERE answered_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
")->fetchColumn();

// Pending queue items
$stats['pending_queue'] = $pdo->query("
    SELECT COUNT(*) FROM ai_question_queue WHERE status = 'pending'
")->fetchColumn();

// Total suggestions
$stats['suggestions'] = $pdo->query("SELECT COUNT(*) FROM ai_suggestions")->fetchColumn();

// Pending suggestions
$stats['pending_suggestions'] = $pdo->query("
    SELECT COUNT(*) FROM ai_suggestions WHERE status = 'pending'
")->fetchColumn();

// Pool profiles
$stats['profiles'] = $pdo->query("SELECT COUNT(*) FROM ai_pool_profiles")->fetchColumn();

// Flagged responses
$stats['flagged'] = $pdo->query("SELECT COUNT(*) FROM ai_responses WHERE flagged = 1")->fetchColumn();

// Get recent responses
$recent_responses = $pdo->query("
    SELECT r.*, q.text as question_text, q.category,
           COALESCE(d.alias, d.name) as device_name
    FROM ai_responses r
    JOIN ai_questions q ON r.question_id = q.id
    JOIN pi_devices d ON r.device_id = d.id
    ORDER BY r.answered_at DESC
    LIMIT 10
")->fetchAll(PDO::FETCH_ASSOC);

// Get recent suggestions
$recent_suggestions = $pdo->query("
    SELECT s.*, COALESCE(d.alias, d.name) as device_name
    FROM ai_suggestions s
    JOIN pi_devices d ON s.device_id = d.id
    ORDER BY s.created_at DESC
    LIMIT 10
")->fetchAll(PDO::FETCH_ASSOC);

// Get Claude API usage (last 7 days)
$api_usage = $pdo->query("
    SELECT
        DATE(created_at) as date,
        COUNT(*) as calls,
        SUM(tokens_used) as tokens,
        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
    FROM ai_conversation_log
    WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
    GROUP BY DATE(created_at)
    ORDER BY date DESC
")->fetchAll(PDO::FETCH_ASSOC);

// Suggestion status distribution
$suggestion_statuses = $pdo->query("
    SELECT status, COUNT(*) as count
    FROM ai_suggestions
    GROUP BY status
")->fetchAll(PDO::FETCH_KEY_PAIR);

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Assistant Dashboard - PoolAIssistant</title>
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

        .nav-links {
            display: flex;
            gap: 8px;
        }
        .nav-links a {
            background: var(--surface-2);
            color: var(--text);
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.875rem;
        }
        .nav-links a:hover { background: var(--border); }
        .nav-links a.active { background: var(--accent); }

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
        .stat-card .value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--accent);
        }
        .stat-card.purple .value { color: var(--purple); }
        .stat-card.success .value { color: var(--success); }
        .stat-card.warning .value { color: var(--warning); }
        .stat-card.danger .value { color: var(--danger); }
        .stat-card .label {
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .grid-2 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 24px;
            margin-bottom: 30px;
        }

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
        }
        .card-body { padding: 16px 20px; }

        .list-item {
            padding: 12px 0;
            border-bottom: 1px solid var(--surface-2);
        }
        .list-item:last-child { border-bottom: none; }
        .list-item .title {
            font-weight: 500;
            margin-bottom: 4px;
        }
        .list-item .meta {
            font-size: 0.875rem;
            color: var(--text-muted);
            display: flex;
            gap: 12px;
        }

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
        .badge.purple { background: rgba(139, 92, 246, 0.2); color: var(--purple); }
        .badge.muted { background: var(--surface-2); color: var(--text-muted); }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 10px 12px;
            text-align: left;
        }
        th {
            font-weight: 600;
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--surface-2);
        }
        tr:not(:last-child) td {
            border-bottom: 1px solid var(--surface-2);
        }

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
        .btn-sm { padding: 4px 8px; font-size: 0.75rem; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); }

        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.875rem; }
        .mono { font-family: 'SF Mono', Monaco, monospace; }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }

        .progress-bar {
            height: 8px;
            background: var(--surface-2);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }
        .progress-bar .fill {
            height: 100%;
            border-radius: 4px;
        }

        @media (max-width: 768px) {
            .grid-2 { grid-template-columns: 1fr; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><span>AI</span> Assistant Dashboard</h1>
            <nav class="nav-links">
                <a href="ai_dashboard.php" class="active">Dashboard</a>
                <a href="ai_questions.php">Questions</a>
                <a href="ai_responses.php">Responses</a>
                <a href="ai_suggestions.php">Suggestions</a>
                <a href="index.php">Devices</a>
            </nav>
        </header>

        <div class="stats-grid">
            <div class="stat-card purple">
                <div class="value"><?= $stats['questions'] ?></div>
                <div class="label">Questions</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['responses'] ?></div>
                <div class="label">Total Responses</div>
            </div>
            <div class="stat-card success">
                <div class="value"><?= $stats['responses_week'] ?></div>
                <div class="label">Responses This Week</div>
            </div>
            <div class="stat-card warning">
                <div class="value"><?= $stats['pending_queue'] ?></div>
                <div class="label">Pending Questions</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['suggestions'] ?></div>
                <div class="label">Total Suggestions</div>
            </div>
            <div class="stat-card warning">
                <div class="value"><?= $stats['pending_suggestions'] ?></div>
                <div class="label">Pending Suggestions</div>
            </div>
            <div class="stat-card purple">
                <div class="value"><?= $stats['profiles'] ?></div>
                <div class="label">Pool Profiles</div>
            </div>
            <div class="stat-card <?= $stats['flagged'] > 0 ? 'danger' : '' ?>">
                <div class="value"><?= $stats['flagged'] ?></div>
                <div class="label">Flagged Responses</div>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <div class="card-header">
                    <h2>Recent Responses</h2>
                    <a href="ai_responses.php" class="btn btn-sm btn-primary">View All</a>
                </div>
                <div class="card-body">
                    <?php if (empty($recent_responses)): ?>
                        <div class="empty-state">No responses yet</div>
                    <?php else: ?>
                        <?php foreach ($recent_responses as $r): ?>
                        <div class="list-item">
                            <div class="title"><?= htmlspecialchars(substr($r['question_text'], 0, 60)) ?>...</div>
                            <div class="meta">
                                <span><?= htmlspecialchars($r['device_name']) ?></span>
                                <span><strong><?= htmlspecialchars(substr($r['answer'], 0, 40)) ?></strong></span>
                                <span><?= date('M j, g:ia', strtotime($r['answered_at'])) ?></span>
                            </div>
                        </div>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2>Recent Suggestions</h2>
                    <a href="ai_suggestions.php" class="btn btn-sm btn-primary">View All</a>
                </div>
                <div class="card-body">
                    <?php if (empty($recent_suggestions)): ?>
                        <div class="empty-state">No suggestions yet</div>
                    <?php else: ?>
                        <?php foreach ($recent_suggestions as $s): ?>
                        <div class="list-item">
                            <div class="title">
                                <?= htmlspecialchars($s['title']) ?>
                                <?php
                                $badge_class = match($s['status']) {
                                    'pending' => 'warning',
                                    'delivered', 'read' => 'purple',
                                    'acted_upon' => 'success',
                                    'dismissed' => 'muted',
                                    'retracted' => 'danger',
                                    default => 'muted'
                                };
                                ?>
                                <span class="badge <?= $badge_class ?>"><?= $s['status'] ?></span>
                            </div>
                            <div class="meta">
                                <span><?= htmlspecialchars($s['device_name']) ?></span>
                                <span><?= $s['suggestion_type'] ?? 'general' ?></span>
                                <span><?= date('M j, g:ia', strtotime($s['created_at'])) ?></span>
                            </div>
                        </div>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </div>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <div class="card-header">
                    <h2>Claude API Usage (7 Days)</h2>
                </div>
                <div class="card-body">
                    <?php if (empty($api_usage)): ?>
                        <div class="empty-state">No API usage recorded</div>
                    <?php else: ?>
                        <table>
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Calls</th>
                                    <th>Tokens</th>
                                    <th>Success Rate</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($api_usage as $u): ?>
                                <tr>
                                    <td><?= date('M j', strtotime($u['date'])) ?></td>
                                    <td class="mono"><?= number_format($u['calls']) ?></td>
                                    <td class="mono"><?= number_format($u['tokens']) ?></td>
                                    <td>
                                        <?php
                                        $rate = $u['calls'] > 0 ? round(($u['successes'] / $u['calls']) * 100) : 0;
                                        $rate_class = $rate >= 95 ? 'success' : ($rate >= 80 ? 'warning' : 'danger');
                                        ?>
                                        <span class="badge <?= $rate_class ?>"><?= $rate ?>%</span>
                                    </td>
                                </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table>
                    <?php endif; ?>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2>Suggestion Status Distribution</h2>
                </div>
                <div class="card-body">
                    <?php if (empty($suggestion_statuses)): ?>
                        <div class="empty-state">No suggestions yet</div>
                    <?php else: ?>
                        <?php
                        $total = array_sum($suggestion_statuses);
                        $status_colors = [
                            'pending' => '#f59e0b',
                            'delivered' => '#8b5cf6',
                            'read' => '#3b82f6',
                            'acted_upon' => '#22c55e',
                            'dismissed' => '#94a3b8',
                            'retracted' => '#ef4444'
                        ];
                        ?>
                        <?php foreach ($suggestion_statuses as $status => $count): ?>
                        <div style="margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; font-size: 0.875rem;">
                                <span style="text-transform: capitalize;"><?= str_replace('_', ' ', $status) ?></span>
                                <span class="text-muted"><?= $count ?> (<?= round(($count / $total) * 100) ?>%)</span>
                            </div>
                            <div class="progress-bar">
                                <div class="fill" style="width: <?= ($count / $total) * 100 ?>%; background: <?= $status_colors[$status] ?? '#3b82f6' ?>;"></div>
                            </div>
                        </div>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </div>
            </div>
        </div>
    </div>

    <script>
    // Auto-refresh every 60 seconds
    setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
