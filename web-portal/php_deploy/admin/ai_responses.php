<?php
/**
 * AI Responses Viewer
 * View and manage user responses to questions
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Check if AI tables exist - redirect to setup if not
try {
    $pdo->query("SELECT 1 FROM ai_responses LIMIT 1");
} catch (PDOException $e) {
    header('Location: ai_setup.php');
    exit;
}

// Get filter values
$device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;
$category = $_GET['category'] ?? null;
$flagged = isset($_GET['flagged']) ? ($_GET['flagged'] === '1') : null;
$from = $_GET['from'] ?? date('Y-m-d', strtotime('-30 days'));
$to = $_GET['to'] ?? date('Y-m-d');

// Build query
$where = ['r.answered_at >= ?', 'r.answered_at <= ?'];
$params = [$from, $to . ' 23:59:59'];

if ($device_id) {
    $where[] = 'r.device_id = ?';
    $params[] = $device_id;
}
if ($category) {
    $where[] = 'q.category = ?';
    $params[] = $category;
}
if ($flagged !== null) {
    $where[] = 'r.flagged = ?';
    $params[] = $flagged ? 1 : 0;
}

$where_clause = 'WHERE ' . implode(' AND ', $where);

// Get responses
$stmt = $pdo->prepare("
    SELECT r.*,
           q.text as question_text,
           q.type as question_type,
           q.category as question_category,
           d.name as device_name,
           d.name as device_alias
    FROM ai_responses r
    JOIN ai_questions q ON r.question_id = q.id
    JOIN pi_devices d ON r.device_id = d.id
    $where_clause
    ORDER BY r.answered_at DESC
    LIMIT 200
");
$stmt->execute($params);
$responses = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Get filter options
$devices = $pdo->query("
    SELECT DISTINCT d.id, d.name as name
    FROM ai_responses r
    JOIN pi_devices d ON r.device_id = d.id
    ORDER BY name
")->fetchAll(PDO::FETCH_ASSOC);

$categories = $pdo->query("
    SELECT DISTINCT q.category
    FROM ai_responses r
    JOIN ai_questions q ON r.question_id = q.id
    WHERE q.category IS NOT NULL
    ORDER BY q.category
")->fetchAll(PDO::FETCH_COLUMN);

// Stats
$total_responses = $pdo->query("SELECT COUNT(*) FROM ai_responses")->fetchColumn();
$flagged_count = $pdo->query("SELECT COUNT(*) FROM ai_responses WHERE flagged = 1")->fetchColumn();

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Responses - PoolAIssistant</title>
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

        .nav-links { display: flex; gap: 8px; }
        .nav-links a {
            background: var(--surface-2);
            color: var(--text);
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.875rem;
        }
        .nav-links a:hover { background: var(--border); }
        .nav-links a.active { background: var(--accent); }

        .filters {
            background: var(--surface);
            padding: 16px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            align-items: flex-end;
        }
        .filter-group { display: flex; flex-direction: column; gap: 4px; }
        .filter-group label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .filter-group select,
        .filter-group input {
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--surface-2);
            color: var(--text);
            font-size: 0.875rem;
            min-width: 150px;
        }
        .filter-group input[type="date"] { min-width: 140px; }

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
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-secondary { background: var(--surface-2); color: var(--text); }
        .btn-sm { padding: 4px 8px; font-size: 0.75rem; }

        .stats-row {
            display: flex;
            gap: 24px;
            margin-bottom: 20px;
            font-size: 0.875rem;
        }
        .stats-row span { color: var(--text-muted); }
        .stats-row strong { color: var(--text); }

        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
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
        .badge.onboarding { background: rgba(139, 92, 246, 0.2); color: var(--purple); }
        .badge.periodic { background: rgba(59, 130, 246, 0.2); color: var(--accent); }
        .badge.event { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge.followup { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge.contextual { background: rgba(148, 163, 184, 0.2); color: var(--text-muted); }
        .badge.flagged { background: rgba(239, 68, 68, 0.2); color: var(--danger); }

        .answer-text {
            background: var(--surface-2);
            padding: 6px 12px;
            border-radius: 6px;
            display: inline-block;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.875rem; }

        .flag-btn {
            background: none;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            opacity: 0.3;
            transition: opacity 0.15s;
        }
        .flag-btn:hover { opacity: 1; }
        .flag-btn.flagged { opacity: 1; color: var(--danger); }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }

        /* Response detail modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        .modal-overlay.show { display: flex; }
        .modal {
            background: var(--surface);
            border-radius: 12px;
            width: 100%;
            max-width: 700px;
            max-height: 90vh;
            overflow-y: auto;
        }
        .modal-header {
            padding: 20px;
            border-bottom: 1px solid var(--surface-2);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h2 { font-size: 1.25rem; }
        .modal-close {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1.5rem;
            cursor: pointer;
        }
        .modal-body { padding: 20px; }
        .detail-row {
            display: flex;
            margin-bottom: 16px;
        }
        .detail-label {
            width: 120px;
            color: var(--text-muted);
            font-size: 0.875rem;
        }
        .detail-value { flex: 1; }

        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--success);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 2000;
            display: none;
        }
        .toast.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><span>AI</span> Responses</h1>
            <nav class="nav-links">
                <a href="ai_dashboard.php">Dashboard</a>
                <a href="ai_questions.php">Questions</a>
                <a href="ai_responses.php" class="active">Responses</a>
                <a href="ai_suggestions.php">Suggestions</a>
                <a href="ai_learnings.php">Learnings</a>
                <a href="ai_settings.php">Settings</a>
                <a href="index.php">Devices</a>
            </nav>
        </header>

        <form class="filters" method="GET">
            <div class="filter-group">
                <label>Device</label>
                <select name="device_id">
                    <option value="">All Devices</option>
                    <?php foreach ($devices as $d): ?>
                    <option value="<?= $d['id'] ?>" <?= $device_id == $d['id'] ? 'selected' : '' ?>>
                        <?= htmlspecialchars($d['name']) ?>
                    </option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="filter-group">
                <label>Category</label>
                <select name="category">
                    <option value="">All Categories</option>
                    <?php foreach ($categories as $c): ?>
                    <option value="<?= $c ?>" <?= $category === $c ? 'selected' : '' ?>>
                        <?= ucfirst($c) ?>
                    </option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="filter-group">
                <label>From</label>
                <input type="date" name="from" value="<?= $from ?>">
            </div>
            <div class="filter-group">
                <label>To</label>
                <input type="date" name="to" value="<?= $to ?>">
            </div>
            <div class="filter-group">
                <label>Status</label>
                <select name="flagged">
                    <option value="">All</option>
                    <option value="1" <?= $flagged === true ? 'selected' : '' ?>>Flagged Only</option>
                    <option value="0" <?= $flagged === false ? 'selected' : '' ?>>Not Flagged</option>
                </select>
            </div>
            <button type="submit" class="btn btn-primary">Filter</button>
            <a href="?export=csv&from=<?= $from ?>&to=<?= $to ?><?= $device_id ? "&device_id=$device_id" : '' ?>" class="btn btn-secondary">Export CSV</a>
        </form>

        <div class="stats-row">
            <span>Showing <strong><?= count($responses) ?></strong> responses</span>
            <span>Total: <strong><?= number_format($total_responses) ?></strong></span>
            <span>Flagged: <strong><?= $flagged_count ?></strong></span>
        </div>

        <?php if (empty($responses)): ?>
            <div class="empty-state">
                <h3>No responses found</h3>
                <p>Adjust your filters or wait for responses to come in.</p>
            </div>
        <?php else: ?>
            <table>
                <thead>
                    <tr>
                        <th>Device</th>
                        <th>Question</th>
                        <th>Answer</th>
                        <th>Category</th>
                        <th>Answered</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($responses as $r): ?>
                    <tr data-id="<?= $r['id'] ?>">
                        <td><?= htmlspecialchars($r['device_alias'] ?: $r['device_name']) ?></td>
                        <td>
                            <span class="badge <?= $r['question_type'] ?>"><?= $r['question_type'] ?></span>
                            <?= htmlspecialchars(substr($r['question_text'], 0, 50)) ?>...
                        </td>
                        <td>
                            <span class="answer-text"><?= htmlspecialchars($r['answer']) ?></span>
                        </td>
                        <td class="text-muted"><?= $r['question_category'] ?? '-' ?></td>
                        <td class="text-muted text-sm"><?= date('M j, g:ia', strtotime($r['answered_at'])) ?></td>
                        <td>
                            <button class="flag-btn <?= $r['flagged'] ? 'flagged' : '' ?>"
                                    onclick="toggleFlag(<?= $r['id'] ?>, this)"
                                    title="<?= $r['flagged'] ? 'Unflag' : 'Flag for review' ?>">
                                &#9873;
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="viewDetail(<?= $r['id'] ?>)">View</button>
                        </td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </div>

    <!-- Detail Modal -->
    <div class="modal-overlay" id="detailModal">
        <div class="modal">
            <div class="modal-header">
                <h2>Response Details</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="detailContent">
                Loading...
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
    function toggleFlag(id, btn) {
        const isFlagged = btn.classList.contains('flagged');

        fetch('/api/ai/responses.php?id=' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ flagged: !isFlagged })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                btn.classList.toggle('flagged');
                showToast(isFlagged ? 'Flag removed' : 'Flagged for review');
            }
        });
    }

    function viewDetail(id) {
        document.getElementById('detailModal').classList.add('show');
        document.getElementById('detailContent').innerHTML = 'Loading...';

        fetch('/api/ai/responses.php?id=' + id)
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    const r = data.response;
                    document.getElementById('detailContent').innerHTML = `
                        <div class="detail-row">
                            <div class="detail-label">Device</div>
                            <div class="detail-value">${r.device_alias || r.device_name}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Pool</div>
                            <div class="detail-value">${r.pool || 'Default'}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Question</div>
                            <div class="detail-value">${r.question_text}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Type</div>
                            <div class="detail-value"><span class="badge ${r.question_type}">${r.question_type}</span></div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Category</div>
                            <div class="detail-value">${r.question_category || 'General'}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Answer</div>
                            <div class="detail-value"><strong>${r.answer}</strong></div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Answered</div>
                            <div class="detail-value">${new Date(r.answered_at).toLocaleString()}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Received</div>
                            <div class="detail-value">${new Date(r.received_at).toLocaleString()}</div>
                        </div>
                        ${r.admin_notes ? `
                        <div class="detail-row">
                            <div class="detail-label">Admin Notes</div>
                            <div class="detail-value">${r.admin_notes}</div>
                        </div>
                        ` : ''}
                        ${r.related_responses && r.related_responses.length > 0 ? `
                        <h3 style="margin: 20px 0 12px; font-size: 1rem;">Related Responses</h3>
                        ${r.related_responses.map(rel => `
                            <div style="background: var(--surface-2); padding: 12px; border-radius: 6px; margin-bottom: 8px;">
                                <div style="font-size: 0.875rem; color: var(--text-muted);">${rel.question_text}</div>
                                <div><strong>${rel.answer}</strong></div>
                                <div style="font-size: 0.75rem; color: var(--text-muted);">${new Date(rel.answered_at).toLocaleDateString()}</div>
                            </div>
                        `).join('')}
                        ` : ''}
                    `;
                }
            });
    }

    function closeModal() {
        document.getElementById('detailModal').classList.remove('show');
    }

    function showToast(message) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3000);
    }

    document.querySelector('.modal-overlay').addEventListener('click', function(e) {
        if (e.target === this) closeModal();
    });
    </script>
</body>
</html>
