<?php
/**
 * AI Suggestions Manager
 * View, review, and manage AI-generated suggestions
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Check if AI tables exist - redirect to setup if not
try {
    $pdo->query("SELECT 1 FROM ai_suggestions LIMIT 1");
} catch (PDOException $e) {
    header('Location: ai_setup.php');
    exit;
}

// Get filter values
$device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;
$status = $_GET['status'] ?? null;
$type = $_GET['type'] ?? null;

// Build query
$where = [];
$params = [];

if ($device_id) {
    $where[] = 's.device_id = ?';
    $params[] = $device_id;
}
if ($status) {
    $where[] = 's.status = ?';
    $params[] = $status;
}
if ($type) {
    $where[] = 's.suggestion_type = ?';
    $params[] = $type;
}

$where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

// Get suggestions
$stmt = $pdo->prepare("
    SELECT s.*,
           d.name as device_name
    FROM ai_suggestions s
    JOIN pi_devices d ON s.device_id = d.id
    $where_clause
    ORDER BY s.created_at DESC
    LIMIT 200
");
$stmt->execute($params);
$suggestions = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Get filter options
$devices = $pdo->query("
    SELECT DISTINCT d.id, d.name as name
    FROM ai_suggestions s
    JOIN pi_devices d ON s.device_id = d.id
    ORDER BY name
")->fetchAll(PDO::FETCH_ASSOC);

$types = $pdo->query("
    SELECT DISTINCT suggestion_type FROM ai_suggestions WHERE suggestion_type IS NOT NULL ORDER BY suggestion_type
")->fetchAll(PDO::FETCH_COLUMN);

// Status counts
$status_counts = $pdo->query("
    SELECT status, COUNT(*) as count FROM ai_suggestions GROUP BY status
")->fetchAll(PDO::FETCH_KEY_PAIR);

// All devices for manual suggestion
$all_devices = $pdo->query("
    SELECT id, COALESCE(name, device_uuid) as name FROM pi_devices WHERE is_active = 1 ORDER BY name
")->fetchAll(PDO::FETCH_ASSOC);

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suggestions - PoolAIssistant</title>
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

        .toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .filters {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
        .filter-group select {
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--surface);
            color: var(--text);
            font-size: 0.875rem;
        }

        .status-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
        .status-tab {
            padding: 6px 12px;
            background: var(--surface);
            border: none;
            border-radius: 6px;
            color: var(--text);
            cursor: pointer;
            font-size: 0.875rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .status-tab:hover { background: var(--surface-2); }
        .status-tab.active { background: var(--purple); }
        .status-tab .count {
            background: var(--surface-2);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.75rem;
        }
        .status-tab.active .count { background: rgba(255,255,255,0.2); }

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
        .btn-danger { background: var(--danger); color: white; }
        .btn-sm { padding: 4px 8px; font-size: 0.75rem; }

        .suggestion-card {
            background: var(--surface);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }
        .suggestion-card.retracted {
            opacity: 0.5;
            border-left: 3px solid var(--danger);
        }
        .suggestion-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }
        .suggestion-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 4px;
        }
        .suggestion-meta {
            display: flex;
            gap: 12px;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .suggestion-body {
            background: var(--surface-2);
            padding: 16px;
            border-radius: 8px;
            margin: 12px 0;
            white-space: pre-wrap;
        }
        .suggestion-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .suggestion-actions { display: flex; gap: 8px; }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge.pending { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge.delivered { background: rgba(139, 92, 246, 0.2); color: var(--purple); }
        .badge.read { background: rgba(59, 130, 246, 0.2); color: var(--accent); }
        .badge.acted_upon { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge.dismissed { background: rgba(148, 163, 184, 0.2); color: var(--text-muted); }
        .badge.retracted { background: rgba(239, 68, 68, 0.2); color: var(--danger); }

        .priority-indicator {
            display: flex;
            gap: 3px;
        }
        .priority-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--surface-2);
        }
        .priority-dot.filled { background: var(--warning); }

        .confidence-bar {
            width: 60px;
            height: 6px;
            background: var(--surface-2);
            border-radius: 3px;
            overflow: hidden;
        }
        .confidence-fill {
            height: 100%;
            background: var(--success);
            border-radius: 3px;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }

        /* Modal */
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
            max-width: 600px;
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
        .modal-footer {
            padding: 20px;
            border-top: 1px solid var(--surface-2);
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }

        .form-group { margin-bottom: 16px; }
        .form-group label {
            display: block;
            margin-bottom: 6px;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 10px 12px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--surface-2);
            color: var(--text);
            font-size: 0.875rem;
        }
        .form-group textarea { min-height: 100px; resize: vertical; }
        .form-row {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
        }

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
        .toast.error { background: var(--danger); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><span>AI</span> Suggestions</h1>
            <nav class="nav-links">
                <a href="ai_dashboard.php">Dashboard</a>
                <a href="ai_questions.php">Questions</a>
                <a href="ai_responses.php">Responses</a>
                <a href="ai_suggestions.php" class="active">Suggestions</a>
                <a href="ai_learnings.php">Learnings</a>
                <a href="ai_settings.php">Settings</a>
                <a href="index.php">Devices</a>
            </nav>
        </header>

        <div class="toolbar">
            <div class="status-tabs">
                <a href="?" class="status-tab <?= !$status ? 'active' : '' ?>">
                    All <span class="count"><?= array_sum($status_counts) ?></span>
                </a>
                <?php foreach (['pending', 'delivered', 'read', 'acted_upon', 'dismissed', 'retracted'] as $s): ?>
                <a href="?status=<?= $s ?><?= $device_id ? "&device_id=$device_id" : '' ?><?= $type ? "&type=$type" : '' ?>"
                   class="status-tab <?= $status === $s ? 'active' : '' ?>">
                    <?= ucfirst(str_replace('_', ' ', $s)) ?>
                    <span class="count"><?= $status_counts[$s] ?? 0 ?></span>
                </a>
                <?php endforeach; ?>
            </div>
            <button class="btn btn-primary" onclick="openCreateModal()">+ Manual Suggestion</button>
        </div>

        <div class="filters" style="margin-bottom: 20px;">
            <div class="filter-group">
                <select onchange="applyFilter('device_id', this.value)">
                    <option value="">All Devices</option>
                    <?php foreach ($devices as $d): ?>
                    <option value="<?= $d['id'] ?>" <?= $device_id == $d['id'] ? 'selected' : '' ?>>
                        <?= htmlspecialchars($d['name']) ?>
                    </option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="filter-group">
                <select onchange="applyFilter('type', this.value)">
                    <option value="">All Types</option>
                    <?php foreach ($types as $t): ?>
                    <option value="<?= $t ?>" <?= $type === $t ? 'selected' : '' ?>>
                        <?= ucfirst($t) ?>
                    </option>
                    <?php endforeach; ?>
                </select>
            </div>
        </div>

        <?php if (empty($suggestions)): ?>
            <div class="empty-state">
                <h3>No suggestions found</h3>
                <p>Suggestions will appear here once generated by the AI system.</p>
            </div>
        <?php else: ?>
            <?php foreach ($suggestions as $s): ?>
            <div class="suggestion-card <?= $s['status'] === 'retracted' ? 'retracted' : '' ?>">
                <div class="suggestion-header">
                    <div>
                        <div class="suggestion-title"><?= htmlspecialchars($s['title']) ?></div>
                        <div class="suggestion-meta">
                            <span><?= htmlspecialchars($s['device_name']) ?></span>
                            <span><?= $s['suggestion_type'] ?? 'general' ?></span>
                            <span>
                                Priority:
                                <span class="priority-indicator">
                                    <?php for ($i = 1; $i <= 5; $i++): ?>
                                    <span class="priority-dot <?= $i <= $s['priority'] ? 'filled' : '' ?>"></span>
                                    <?php endfor; ?>
                                </span>
                            </span>
                            <?php if ($s['confidence']): ?>
                            <span>
                                Confidence:
                                <span class="confidence-bar">
                                    <span class="confidence-fill" style="width: <?= $s['confidence'] * 100 ?>%"></span>
                                </span>
                                <?= round($s['confidence'] * 100) ?>%
                            </span>
                            <?php endif; ?>
                        </div>
                    </div>
                    <span class="badge <?= $s['status'] ?>"><?= str_replace('_', ' ', $s['status']) ?></span>
                </div>

                <div class="suggestion-body"><?= htmlspecialchars($s['body']) ?></div>

                <?php if ($s['status'] === 'retracted' && $s['retracted_reason']): ?>
                <div style="color: var(--danger); font-size: 0.875rem; margin-bottom: 12px;">
                    Retracted: <?= htmlspecialchars($s['retracted_reason']) ?>
                </div>
                <?php endif; ?>

                <?php if ($s['user_feedback']): ?>
                <div style="background: rgba(34, 197, 94, 0.1); padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                    <strong>User Feedback:</strong> <?= htmlspecialchars($s['user_feedback']) ?>
                </div>
                <?php endif; ?>

                <div class="suggestion-footer">
                    <div>
                        Created: <?= date('M j, Y g:ia', strtotime($s['created_at'])) ?>
                        <?php if ($s['delivered_at']): ?>
                        | Delivered: <?= date('M j, g:ia', strtotime($s['delivered_at'])) ?>
                        <?php endif; ?>
                        <?php if ($s['read_at']): ?>
                        | Read: <?= date('M j, g:ia', strtotime($s['read_at'])) ?>
                        <?php endif; ?>
                    </div>
                    <div class="suggestion-actions">
                        <?php if ($s['status'] !== 'retracted'): ?>
                        <button class="btn btn-danger btn-sm" onclick="retractSuggestion(<?= $s['id'] ?>)">Retract</button>
                        <?php endif; ?>
                    </div>
                </div>
            </div>
            <?php endforeach; ?>
        <?php endif; ?>
    </div>

    <!-- Create Modal -->
    <div class="modal-overlay" id="createModal">
        <div class="modal">
            <div class="modal-header">
                <h2>Create Manual Suggestion</h2>
                <button class="modal-close" onclick="closeCreateModal()">&times;</button>
            </div>
            <form id="createForm">
                <div class="modal-body">
                    <div class="form-row">
                        <div class="form-group">
                            <label>Device *</label>
                            <select id="createDevice" name="device_id" required>
                                <option value="">Select device...</option>
                                <?php foreach ($all_devices as $d): ?>
                                <option value="<?= $d['id'] ?>"><?= htmlspecialchars($d['name']) ?></option>
                                <?php endforeach; ?>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Pool</label>
                            <input type="text" id="createPool" name="pool" placeholder="Leave empty for default">
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Title *</label>
                        <input type="text" id="createTitle" name="title" required placeholder="Short descriptive title">
                    </div>

                    <div class="form-group">
                        <label>Body *</label>
                        <textarea id="createBody" name="body" required placeholder="Detailed suggestion text..."></textarea>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Type</label>
                            <select id="createType" name="suggestion_type">
                                <option value="manual">Manual</option>
                                <option value="water_quality">Water Quality</option>
                                <option value="dosing">Dosing</option>
                                <option value="maintenance">Maintenance</option>
                                <option value="equipment">Equipment</option>
                                <option value="operational">Operational</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Priority</label>
                            <select id="createPriority" name="priority">
                                <option value="1">1 - Highest</option>
                                <option value="2">2 - High</option>
                                <option value="3" selected>3 - Medium</option>
                                <option value="4">4 - Low</option>
                                <option value="5">5 - Lowest</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Admin Notes</label>
                        <input type="text" id="createNotes" name="admin_notes" placeholder="Internal notes">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="closeCreateModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Create Suggestion</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Retract Modal -->
    <div class="modal-overlay" id="retractModal">
        <div class="modal" style="max-width: 400px;">
            <div class="modal-header">
                <h2>Retract Suggestion</h2>
                <button class="modal-close" onclick="closeRetractModal()">&times;</button>
            </div>
            <form id="retractForm">
                <div class="modal-body">
                    <input type="hidden" id="retractId">
                    <div class="form-group">
                        <label>Reason for retracting</label>
                        <textarea id="retractReason" name="reason" placeholder="Why is this suggestion being retracted?"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="closeRetractModal()">Cancel</button>
                    <button type="submit" class="btn btn-danger">Retract</button>
                </div>
            </form>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
    function applyFilter(key, value) {
        const params = new URLSearchParams(window.location.search);
        if (value) {
            params.set(key, value);
        } else {
            params.delete(key);
        }
        window.location.search = params.toString();
    }

    function openCreateModal() {
        document.getElementById('createModal').classList.add('show');
    }

    function closeCreateModal() {
        document.getElementById('createModal').classList.remove('show');
    }

    document.getElementById('createForm').addEventListener('submit', function(e) {
        e.preventDefault();

        const data = {
            device_id: parseInt(document.getElementById('createDevice').value),
            pool: document.getElementById('createPool').value,
            title: document.getElementById('createTitle').value,
            body: document.getElementById('createBody').value,
            suggestion_type: document.getElementById('createType').value,
            priority: parseInt(document.getElementById('createPriority').value),
            admin_notes: document.getElementById('createNotes').value
        };

        fetch('/api/ai/suggestions.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(r => r.json())
        .then(result => {
            if (result.ok) {
                showToast('Suggestion created');
                closeCreateModal();
                location.reload();
            } else {
                showToast(result.error || 'Error creating suggestion', true);
            }
        });
    });

    function retractSuggestion(id) {
        document.getElementById('retractId').value = id;
        document.getElementById('retractModal').classList.add('show');
    }

    function closeRetractModal() {
        document.getElementById('retractModal').classList.remove('show');
    }

    document.getElementById('retractForm').addEventListener('submit', function(e) {
        e.preventDefault();

        const id = document.getElementById('retractId').value;
        const reason = document.getElementById('retractReason').value;

        fetch('/api/ai/suggestions.php?id=' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ retract: true, retracted_reason: reason })
        })
        .then(r => r.json())
        .then(result => {
            if (result.ok) {
                showToast('Suggestion retracted');
                closeRetractModal();
                location.reload();
            } else {
                showToast(result.error || 'Error retracting suggestion', true);
            }
        });
    });

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast show' + (isError ? ' error' : '');
        setTimeout(() => toast.classList.remove('show'), 3000);
    }

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', function(e) {
            if (e.target === this) {
                this.classList.remove('show');
            }
        });
    });
    </script>
</body>
</html>
