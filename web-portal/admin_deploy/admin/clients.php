<?php
/**
 * PoolAIssistant Admin Panel - Client Management
 * Lists all portal clients with search, filter, and actions
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AdminClients.php';

// Require admin login
requireAdmin();

$adminClients = new AdminClients();

// Get filter parameters
$search = trim($_GET['search'] ?? '');
$status = $_GET['status'] ?? '';
$page = max(1, intval($_GET['page'] ?? 1));
$sortBy = $_GET['sort'] ?? 'created_at';
$sortDir = $_GET['dir'] ?? 'DESC';

// Temporary diagnostic: ?debug=1 surfaces PDO/schema errors as plain text
// instead of the generic 500 page. Safe to leave in; guarded by admin auth above.
try {
    $result = $adminClients->listClients([
        'search' => $search,
        'status' => $status,
        'page' => $page,
        'sort_by' => $sortBy,
        'sort_dir' => $sortDir,
    ]);
    $stats = $adminClients->getStats();
} catch (Throwable $e) {
    if (isset($_GET['debug'])) {
        header('Content-Type: text/plain; charset=utf-8');
        echo "clients.php failed\n";
        echo "===================\n\n";
        echo "Exception: " . get_class($e) . "\n";
        echo "Message:   " . $e->getMessage() . "\n";
        echo "File:      " . $e->getFile() . ":" . $e->getLine() . "\n\n";
        echo "Trace:\n" . $e->getTraceAsString() . "\n";
        exit;
    }
    throw $e;
}

$clients = $result['clients'];
$total = $result['total'];
$totalPages = $result['total_pages'];

// Helper for sort links
function sortLink($column, $currentSort, $currentDir) {
    $newDir = ($currentSort === $column && $currentDir === 'ASC') ? 'DESC' : 'ASC';
    $params = $_GET;
    $params['sort'] = $column;
    $params['dir'] = $newDir;
    return '?' . http_build_query($params);
}

function sortIcon($column, $currentSort, $currentDir) {
    if ($currentSort !== $column) return '';
    return $currentDir === 'ASC' ? ' ▲' : ' ▼';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Client Management - PoolAIssistant Admin</title>
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
        .nav-links { display: flex; gap: 8px; }
        .nav-link {
            background: var(--surface-2);
            color: var(--text);
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.875rem;
        }
        .nav-link:hover { background: var(--border); }
        .nav-link.active { background: var(--accent); }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--surface);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-card .value { font-size: 1.75rem; font-weight: 700; color: var(--accent); }
        .stat-card .label { font-size: 0.75rem; color: var(--text-muted); margin-top: 4px; text-transform: uppercase; }

        .filters {
            background: var(--surface);
            padding: 16px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filters input, .filters select {
            background: var(--surface-2);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.875rem;
        }
        .filters input { width: 250px; }
        .filters input::placeholder { color: var(--text-muted); }
        .filters input:focus, .filters select:focus {
            outline: none;
            border-color: var(--accent);
        }
        .btn {
            display: inline-block;
            padding: 8px 16px;
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
        .btn-danger { background: var(--danger); color: white; }
        .btn-warning { background: var(--warning); color: #000; }
        .btn-success { background: var(--success); color: white; }

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
        th a { color: var(--text-muted); text-decoration: none; }
        th a:hover { color: var(--text); }
        tr:not(:last-child) td { border-bottom: 1px solid var(--surface-2); }
        tr:hover td { background: rgba(59, 130, 246, 0.05); }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge.active { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge.suspended { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .badge.pending { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge.comp { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }
        .badge.trialing { background: rgba(59, 130, 246, 0.2); color: var(--accent); }

        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.875rem; }
        .mono { font-family: 'SF Mono', Monaco, monospace; font-size: 0.8rem; }

        .pagination {
            display: flex;
            justify-content: center;
            gap: 8px;
            margin-top: 20px;
        }
        .pagination a, .pagination span {
            padding: 8px 12px;
            background: var(--surface);
            border-radius: 6px;
            text-decoration: none;
            color: var(--text);
            font-size: 0.875rem;
        }
        .pagination a:hover { background: var(--surface-2); }
        .pagination .current { background: var(--accent); }
        .pagination .disabled { opacity: 0.5; pointer-events: none; }

        .actions { display: flex; gap: 4px; }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }

        @media (max-width: 768px) {
            .container { padding: 12px; }
            .filters { flex-direction: column; }
            .filters input { width: 100%; }
            table { font-size: 0.8rem; }
            th, td { padding: 8px 10px; }
            .hide-mobile { display: none; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Pool<span>AI</span>ssistant - Clients</h1>
            <nav class="nav-links">
                <a href="index.php" class="nav-link">Devices</a>
                <a href="clients.php" class="nav-link active">Clients</a>
                <a href="ai_dashboard.php" class="nav-link">AI</a>
                <a href="logout.php" class="nav-link">Logout</a>
            </nav>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="value"><?= $stats['total_clients'] ?></div>
                <div class="label">Total Clients</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['active_clients'] ?></div>
                <div class="label">Active</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['subscribed_clients'] ?></div>
                <div class="label">Subscribed</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['comped_clients'] ?></div>
                <div class="label">Comped</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['total_linked_devices'] ?></div>
                <div class="label">Linked Devices</div>
            </div>
            <div class="stat-card">
                <div class="value"><?= $stats['new_this_month'] ?></div>
                <div class="label">New This Month</div>
            </div>
        </div>

        <form class="filters" method="GET">
            <input type="text" name="search" placeholder="Search by email, name, or company..."
                   value="<?= htmlspecialchars($search) ?>">
            <select name="status">
                <option value="">All Status</option>
                <option value="active" <?= $status === 'active' ? 'selected' : '' ?>>Active</option>
                <option value="pending" <?= $status === 'pending' ? 'selected' : '' ?>>Pending</option>
                <option value="suspended" <?= $status === 'suspended' ? 'selected' : '' ?>>Suspended</option>
            </select>
            <button type="submit" class="btn btn-primary">Filter</button>
            <?php if ($search || $status): ?>
            <a href="clients.php" class="btn btn-secondary">Clear</a>
            <?php endif; ?>
        </form>

        <?php if (empty($clients)): ?>
        <div class="empty-state">
            <h3>No clients found</h3>
            <p>No clients match your search criteria.</p>
        </div>
        <?php else: ?>
        <table>
            <thead>
                <tr>
                    <th><a href="<?= sortLink('email', $sortBy, $sortDir) ?>">Email<?= sortIcon('email', $sortBy, $sortDir) ?></a></th>
                    <th><a href="<?= sortLink('name', $sortBy, $sortDir) ?>">Name<?= sortIcon('name', $sortBy, $sortDir) ?></a></th>
                    <th class="hide-mobile"><a href="<?= sortLink('company', $sortBy, $sortDir) ?>">Company<?= sortIcon('company', $sortBy, $sortDir) ?></a></th>
                    <th><a href="<?= sortLink('device_count', $sortBy, $sortDir) ?>">Devices<?= sortIcon('device_count', $sortBy, $sortDir) ?></a></th>
                    <th><a href="<?= sortLink('status', $sortBy, $sortDir) ?>">Status<?= sortIcon('status', $sortBy, $sortDir) ?></a></th>
                    <th class="hide-mobile">Subscription</th>
                    <th class="hide-mobile"><a href="<?= sortLink('last_login_at', $sortBy, $sortDir) ?>">Last Login<?= sortIcon('last_login_at', $sortBy, $sortDir) ?></a></th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($clients as $client): ?>
                <tr>
                    <td>
                        <a href="client_detail.php?id=<?= $client['id'] ?>" style="color: var(--accent);">
                            <?= htmlspecialchars($client['email']) ?>
                        </a>
                        <?php if (!$client['email_verified']): ?>
                        <span class="badge pending" style="margin-left: 4px;">Unverified</span>
                        <?php endif; ?>
                    </td>
                    <td><?= htmlspecialchars($client['name'] ?: '-') ?></td>
                    <td class="hide-mobile text-muted"><?= htmlspecialchars($client['company'] ?: '-') ?></td>
                    <td>
                        <?php if ($client['device_count'] > 0): ?>
                        <span class="badge active"><?= $client['device_count'] ?></span>
                        <?php else: ?>
                        <span class="text-muted">0</span>
                        <?php endif; ?>
                    </td>
                    <td>
                        <span class="badge <?= $client['status'] ?>">
                            <?= ucfirst($client['status']) ?>
                        </span>
                        <?php if ($client['subscription_override'] === 'comp'): ?>
                        <span class="badge comp">Comp</span>
                        <?php endif; ?>
                    </td>
                    <td class="hide-mobile">
                        <?php if ($client['plan_name']): ?>
                        <span class="badge <?= $client['subscription_status'] ?>">
                            <?= htmlspecialchars($client['plan_name']) ?>
                        </span>
                        <?php else: ?>
                        <span class="text-muted">None</span>
                        <?php endif; ?>
                    </td>
                    <td class="hide-mobile text-muted text-sm">
                        <?php if ($client['last_login_at']): ?>
                        <?= date('M j, Y', strtotime($client['last_login_at'])) ?>
                        <?php else: ?>
                        Never
                        <?php endif; ?>
                    </td>
                    <td class="actions">
                        <a href="client_detail.php?id=<?= $client['id'] ?>" class="btn btn-sm btn-secondary">View</a>
                        <?php if ($client['status'] === 'active'): ?>
                        <button class="btn btn-sm btn-warning"
                                onclick="suspendClient(<?= $client['id'] ?>, '<?= htmlspecialchars($client['email'], ENT_QUOTES) ?>')">
                            Suspend
                        </button>
                        <?php elseif ($client['status'] === 'suspended'): ?>
                        <button class="btn btn-sm btn-success"
                                onclick="activateClient(<?= $client['id'] ?>)">
                            Activate
                        </button>
                        <?php endif; ?>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>

        <?php if ($totalPages > 1): ?>
        <div class="pagination">
            <?php if ($page > 1): ?>
            <a href="?<?= http_build_query(array_merge($_GET, ['page' => $page - 1])) ?>">&laquo; Prev</a>
            <?php else: ?>
            <span class="disabled">&laquo; Prev</span>
            <?php endif; ?>

            <?php
            $start = max(1, $page - 2);
            $end = min($totalPages, $page + 2);
            for ($i = $start; $i <= $end; $i++):
            ?>
            <a href="?<?= http_build_query(array_merge($_GET, ['page' => $i])) ?>"
               class="<?= $i === $page ? 'current' : '' ?>">
                <?= $i ?>
            </a>
            <?php endfor; ?>

            <?php if ($page < $totalPages): ?>
            <a href="?<?= http_build_query(array_merge($_GET, ['page' => $page + 1])) ?>">Next &raquo;</a>
            <?php else: ?>
            <span class="disabled">Next &raquo;</span>
            <?php endif; ?>
        </div>
        <?php endif; ?>

        <p class="text-muted text-sm" style="text-align: center; margin-top: 16px;">
            Showing <?= count($clients) ?> of <?= $total ?> clients
        </p>
        <?php endif; ?>
    </div>

    <script>
    function suspendClient(id, email) {
        const reason = prompt('Reason for suspending ' + email + ':');
        if (reason === null) return;

        fetch('/api/admin/client_actions.php/' + id + '/suspend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason })
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

    function activateClient(id) {
        if (!confirm('Activate this account?')) return;

        fetch('/api/admin/client_actions.php/' + id + '/activate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
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
    </script>
</body>
</html>
