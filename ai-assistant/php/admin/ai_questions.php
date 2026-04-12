<?php
/**
 * AI Questions Library Manager
 * Create, edit, and manage question templates
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Get all questions with stats
$stmt = $pdo->query("
    SELECT q.*,
           p.text as parent_text,
           (SELECT COUNT(*) FROM ai_responses r WHERE r.question_id = q.id) as response_count,
           (SELECT COUNT(*) FROM ai_question_queue qq WHERE qq.question_id = q.id AND qq.status = 'pending') as pending_count
    FROM ai_questions q
    LEFT JOIN ai_questions p ON q.follow_up_to = p.id
    ORDER BY q.type, q.priority DESC, q.id
");
$questions = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Group by type
$grouped = [];
foreach ($questions as $q) {
    $grouped[$q['type']][] = $q;
}

// Get type counts
$type_counts = [];
foreach ($grouped as $type => $qs) {
    $type_counts[$type] = count($qs);
}

// Get all devices for queue modal
$devices = $pdo->query("
    SELECT id, COALESCE(alias, name, device_id) as name FROM pi_devices WHERE is_active = 1 ORDER BY name
")->fetchAll(PDO::FETCH_ASSOC);

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Question Library - PoolAIssistant</title>
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
        }
        .type-tabs { display: flex; gap: 8px; }
        .type-tab {
            padding: 8px 16px;
            background: var(--surface);
            border: none;
            border-radius: 6px;
            color: var(--text);
            cursor: pointer;
            font-size: 0.875rem;
        }
        .type-tab:hover { background: var(--surface-2); }
        .type-tab.active { background: var(--purple); }
        .type-tab .count {
            margin-left: 6px;
            background: var(--surface-2);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.75rem;
        }
        .type-tab.active .count { background: rgba(255,255,255,0.2); }

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
        .btn-secondary:hover { background: var(--border); }
        .btn-danger { background: var(--danger); color: white; }
        .btn-sm { padding: 4px 8px; font-size: 0.75rem; }

        .question-card {
            background: var(--surface);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }
        .question-card.inactive { opacity: 0.5; }
        .question-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }
        .question-text {
            font-size: 1rem;
            font-weight: 500;
            flex: 1;
        }
        .question-meta {
            display: flex;
            gap: 16px;
            font-size: 0.875rem;
            color: var(--text-muted);
            margin-bottom: 12px;
        }
        .question-meta strong { color: var(--text); }
        .question-options {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }
        .option-chip {
            background: var(--surface-2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.875rem;
        }
        .question-actions {
            display: flex;
            gap: 8px;
        }

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

        .priority-dots {
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
        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: var(--accent);
        }
        .form-group textarea { min-height: 100px; resize: vertical; }
        .form-row {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
        }
        .help-text {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
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
            <h1><span>AI</span> Question Library</h1>
            <nav class="nav-links">
                <a href="ai_dashboard.php">Dashboard</a>
                <a href="ai_questions.php" class="active">Questions</a>
                <a href="ai_responses.php">Responses</a>
                <a href="ai_suggestions.php">Suggestions</a>
                <a href="index.php">Devices</a>
            </nav>
        </header>

        <div class="toolbar">
            <div class="type-tabs">
                <button class="type-tab active" data-type="all">
                    All <span class="count"><?= count($questions) ?></span>
                </button>
                <?php foreach (['onboarding', 'periodic', 'event', 'followup', 'contextual'] as $type): ?>
                <button class="type-tab" data-type="<?= $type ?>">
                    <?= ucfirst($type) ?>
                    <span class="count"><?= $type_counts[$type] ?? 0 ?></span>
                </button>
                <?php endforeach; ?>
            </div>
            <button class="btn btn-primary" onclick="openModal()">+ New Question</button>
        </div>

        <div id="questions-list">
            <?php if (empty($questions)): ?>
                <div class="empty-state">
                    <h3>No questions yet</h3>
                    <p>Create your first question to get started.</p>
                </div>
            <?php else: ?>
                <?php foreach ($questions as $q): ?>
                <div class="question-card <?= $q['is_active'] ? '' : 'inactive' ?>" data-type="<?= $q['type'] ?>">
                    <div class="question-header">
                        <div class="question-text">
                            <?= htmlspecialchars($q['text']) ?>
                        </div>
                        <div class="question-actions">
                            <button class="btn btn-secondary btn-sm" onclick="queueQuestion(<?= $q['id'] ?>)">Queue</button>
                            <button class="btn btn-secondary btn-sm" onclick="editQuestion(<?= $q['id'] ?>)">Edit</button>
                            <?php if ($q['is_active']): ?>
                            <button class="btn btn-danger btn-sm" onclick="deleteQuestion(<?= $q['id'] ?>)">Delete</button>
                            <?php endif; ?>
                        </div>
                    </div>
                    <div class="question-meta">
                        <span><span class="badge <?= $q['type'] ?>"><?= $q['type'] ?></span></span>
                        <span><strong><?= $q['category'] ?? 'general' ?></strong></span>
                        <span>Input: <?= $q['input_type'] ?></span>
                        <span>Frequency: <?= $q['frequency'] ?? 'once' ?></span>
                        <span>
                            Priority:
                            <span class="priority-dots">
                                <?php for ($i = 1; $i <= 5; $i++): ?>
                                <span class="priority-dot <?= $i <= $q['priority'] ? 'filled' : '' ?>"></span>
                                <?php endfor; ?>
                            </span>
                        </span>
                        <span><?= $q['response_count'] ?> responses</span>
                        <?php if ($q['pending_count'] > 0): ?>
                        <span class="badge" style="background: rgba(245,158,11,0.2); color: var(--warning);">
                            <?= $q['pending_count'] ?> pending
                        </span>
                        <?php endif; ?>
                    </div>
                    <?php if ($q['options_json']): ?>
                    <div class="question-options">
                        <?php foreach (json_decode($q['options_json'], true) as $opt): ?>
                        <span class="option-chip"><?= htmlspecialchars($opt) ?></span>
                        <?php endforeach; ?>
                    </div>
                    <?php endif; ?>
                    <?php if ($q['admin_notes']): ?>
                    <div style="margin-top: 12px; font-size: 0.875rem; color: var(--text-muted); font-style: italic;">
                        Note: <?= htmlspecialchars($q['admin_notes']) ?>
                    </div>
                    <?php endif; ?>
                </div>
                <?php endforeach; ?>
            <?php endif; ?>
        </div>
    </div>

    <!-- Question Modal -->
    <div class="modal-overlay" id="questionModal">
        <div class="modal">
            <div class="modal-header">
                <h2 id="modalTitle">New Question</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <form id="questionForm">
                <div class="modal-body">
                    <input type="hidden" id="questionId" name="id">

                    <div class="form-group">
                        <label>Question Text *</label>
                        <textarea id="questionText" name="text" required placeholder="What would you like to ask?"></textarea>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Type *</label>
                            <select id="questionType" name="type" required>
                                <option value="onboarding">Onboarding</option>
                                <option value="periodic">Periodic</option>
                                <option value="event">Event-driven</option>
                                <option value="followup">Follow-up</option>
                                <option value="contextual">Contextual</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Category</label>
                            <select id="questionCategory" name="category">
                                <option value="">General</option>
                                <option value="water_quality">Water Quality</option>
                                <option value="equipment">Equipment</option>
                                <option value="maintenance">Maintenance</option>
                                <option value="environment">Environment</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Input Type *</label>
                            <select id="questionInputType" name="input_type" required>
                                <option value="buttons">Buttons</option>
                                <option value="dropdown">Dropdown</option>
                                <option value="text">Text</option>
                                <option value="number">Number</option>
                                <option value="date">Date</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Frequency</label>
                            <select id="questionFrequency" name="frequency">
                                <option value="once">Once</option>
                                <option value="daily">Daily</option>
                                <option value="weekly">Weekly</option>
                                <option value="monthly">Monthly</option>
                                <option value="on_event">On Event</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Options (for buttons/dropdown)</label>
                        <textarea id="questionOptions" name="options" placeholder="Enter each option on a new line"></textarea>
                        <div class="help-text">One option per line. Leave empty for text/number/date inputs.</div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Priority (1-5)</label>
                            <select id="questionPriority" name="priority">
                                <option value="1">1 - Highest</option>
                                <option value="2">2 - High</option>
                                <option value="3" selected>3 - Medium</option>
                                <option value="4">4 - Low</option>
                                <option value="5">5 - Lowest</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Follow-up to</label>
                            <select id="questionFollowUp" name="follow_up_to">
                                <option value="">None</option>
                                <?php foreach ($questions as $q): ?>
                                <option value="<?= $q['id'] ?>"><?= htmlspecialchars(substr($q['text'], 0, 50)) ?>...</option>
                                <?php endforeach; ?>
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Admin Notes</label>
                        <textarea id="questionNotes" name="admin_notes" placeholder="Internal notes about this question"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save Question</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Queue Modal -->
    <div class="modal-overlay" id="queueModal">
        <div class="modal" style="max-width: 400px;">
            <div class="modal-header">
                <h2>Queue Question</h2>
                <button class="modal-close" onclick="closeQueueModal()">&times;</button>
            </div>
            <form id="queueForm">
                <div class="modal-body">
                    <input type="hidden" id="queueQuestionId" name="question_id">

                    <div class="form-group">
                        <label>Device *</label>
                        <select id="queueDevice" name="device_id" required>
                            <option value="">Select device...</option>
                            <?php foreach ($devices as $d): ?>
                            <option value="<?= $d['id'] ?>"><?= htmlspecialchars($d['name']) ?></option>
                            <?php endforeach; ?>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Pool (optional)</label>
                        <input type="text" id="queuePool" name="pool" placeholder="Leave empty for default">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="closeQueueModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Queue Question</button>
                </div>
            </form>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
    // Type filtering
    document.querySelectorAll('.type-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.type-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const type = tab.dataset.type;
            document.querySelectorAll('.question-card').forEach(card => {
                if (type === 'all' || card.dataset.type === type) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    });

    // Modal functions
    function openModal(questionId = null) {
        document.getElementById('questionModal').classList.add('show');
        document.getElementById('modalTitle').textContent = questionId ? 'Edit Question' : 'New Question';
        document.getElementById('questionForm').reset();
        document.getElementById('questionId').value = questionId || '';
    }

    function closeModal() {
        document.getElementById('questionModal').classList.remove('show');
    }

    function editQuestion(id) {
        fetch('/api/ai/questions.php?id=' + id)
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    const q = data.question;
                    document.getElementById('questionId').value = q.id;
                    document.getElementById('questionText').value = q.text;
                    document.getElementById('questionType').value = q.type;
                    document.getElementById('questionCategory').value = q.category || '';
                    document.getElementById('questionInputType').value = q.input_type;
                    document.getElementById('questionFrequency').value = q.frequency || 'once';
                    document.getElementById('questionPriority').value = q.priority;
                    document.getElementById('questionFollowUp').value = q.follow_up_to || '';
                    document.getElementById('questionNotes').value = q.admin_notes || '';

                    if (q.options) {
                        document.getElementById('questionOptions').value = q.options.join('\n');
                    }

                    document.getElementById('modalTitle').textContent = 'Edit Question';
                    document.getElementById('questionModal').classList.add('show');
                }
            });
    }

    function deleteQuestion(id) {
        if (!confirm('Delete this question?')) return;

        fetch('/api/ai/questions.php?id=' + id, { method: 'DELETE' })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    showToast('Question deleted');
                    location.reload();
                } else {
                    showToast(data.error || 'Error deleting question', true);
                }
            });
    }

    // Queue functions
    function queueQuestion(id) {
        document.getElementById('queueQuestionId').value = id;
        document.getElementById('queueModal').classList.add('show');
    }

    function closeQueueModal() {
        document.getElementById('queueModal').classList.remove('show');
    }

    document.getElementById('queueForm').addEventListener('submit', function(e) {
        e.preventDefault();

        const data = {
            question_id: parseInt(document.getElementById('queueQuestionId').value),
            device_id: parseInt(document.getElementById('queueDevice').value),
            pool: document.getElementById('queuePool').value
        };

        fetch('/api/ai/queue.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(r => r.json())
        .then(result => {
            if (result.ok) {
                showToast('Question queued');
                closeQueueModal();
            } else {
                showToast(result.error || 'Error queuing question', true);
            }
        });
    });

    // Form submission
    document.getElementById('questionForm').addEventListener('submit', function(e) {
        e.preventDefault();

        const id = document.getElementById('questionId').value;
        const options = document.getElementById('questionOptions').value.trim()
            .split('\n')
            .filter(o => o.trim());

        const data = {
            text: document.getElementById('questionText').value,
            type: document.getElementById('questionType').value,
            category: document.getElementById('questionCategory').value || null,
            input_type: document.getElementById('questionInputType').value,
            frequency: document.getElementById('questionFrequency').value,
            priority: parseInt(document.getElementById('questionPriority').value),
            follow_up_to: document.getElementById('questionFollowUp').value || null,
            admin_notes: document.getElementById('questionNotes').value || null,
            options: options.length > 0 ? options : null
        };

        const url = id ? '/api/ai/questions.php?id=' + id : '/api/ai/questions.php';
        const method = id ? 'PUT' : 'POST';

        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(r => r.json())
        .then(result => {
            if (result.ok) {
                showToast(id ? 'Question updated' : 'Question created');
                closeModal();
                location.reload();
            } else {
                showToast(result.error || 'Error saving question', true);
            }
        });
    });

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast show' + (isError ? ' error' : '');
        setTimeout(() => toast.classList.remove('show'), 3000);
    }

    // Close modals on overlay click
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
