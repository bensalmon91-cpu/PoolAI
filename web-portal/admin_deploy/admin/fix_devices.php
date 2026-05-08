<?php
/**
 * Fix Device Table - adds missing columns and shows device status
 * DELETE AFTER USE
 */
require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();
$message = '';
$error = '';

// Handle actions
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';

    if ($action === 'add_columns') {
        try {
            // Check if alias column exists
            $columns = $pdo->query("SHOW COLUMNS FROM pi_devices LIKE 'alias'")->fetch();
            if (!$columns) {
                $pdo->exec("ALTER TABLE pi_devices ADD COLUMN alias VARCHAR(100) DEFAULT NULL AFTER name");
                $message .= "Added 'alias' column. ";
            } else {
                $message .= "'alias' column already exists. ";
            }

            // Check if alias_updated_at column exists
            $columns = $pdo->query("SHOW COLUMNS FROM pi_devices LIKE 'alias_updated_at'")->fetch();
            if (!$columns) {
                $pdo->exec("ALTER TABLE pi_devices ADD COLUMN alias_updated_at TIMESTAMP NULL AFTER alias");
                $message .= "Added 'alias_updated_at' column. ";
            } else {
                $message .= "'alias_updated_at' column already exists. ";
            }

            $message .= "Done!";
        } catch (PDOException $e) {
            $error = "Error: " . $e->getMessage();
        }
    }

    if ($action === 'clear_issues') {
        $device_id = (int)$_POST['device_id'];
        try {
            // Clear has_issues flag on latest health record
            $pdo->prepare("
                UPDATE device_health
                SET has_issues = 0, issues_json = NULL
                WHERE device_id = ?
                ORDER BY ts DESC
                LIMIT 1
            ")->execute([$device_id]);
            $message = "Cleared issues for device $device_id";
        } catch (PDOException $e) {
            $error = "Error: " . $e->getMessage();
        }
    }
}

// Get current column status
$has_alias = (bool)$pdo->query("SHOW COLUMNS FROM pi_devices LIKE 'alias'")->fetch();
$has_alias_updated = (bool)$pdo->query("SHOW COLUMNS FROM pi_devices LIKE 'alias_updated_at'")->fetch();

// Get devices with their health data
$devices = $pdo->query("
    SELECT
        d.id,
        d.name,
        d.device_uuid,
        d.last_seen,
        h.has_issues,
        h.issues_json,
        h.alarms_total,
        h.alarms_critical,
        h.controllers_offline,
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
    ORDER BY d.name
")->fetchAll(PDO::FETCH_ASSOC);

?>
<!DOCTYPE html>
<html>
<head>
    <title>Fix Devices - PoolAIssistant</title>
    <style>
        body { font-family: system-ui; background: #0f172a; color: #f1f5f9; padding: 20px; }
        .card { background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px; }
        .btn { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: 500; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-danger { background: #ef4444; color: white; }
        .btn-sm { padding: 6px 12px; font-size: 0.875rem; }
        .message { padding: 12px; border-radius: 8px; margin-bottom: 16px; }
        .message.success { background: rgba(34,197,94,0.1); color: #22c55e; }
        .message.error { background: rgba(239,68,68,0.1); color: #ef4444; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
        .status { padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .status.ok { background: rgba(34,197,94,0.2); color: #22c55e; }
        .status.issues { background: rgba(239,68,68,0.2); color: #ef4444; }
        .status.missing { background: rgba(245,158,11,0.2); color: #f59e0b; }
        pre { background: #0f172a; padding: 10px; border-radius: 6px; font-size: 0.8rem; overflow-x: auto; }
        a { color: #3b82f6; }
    </style>
</head>
<body>
    <h1>Fix Device Table</h1>

    <?php if ($message): ?>
        <div class="message success"><?= htmlspecialchars($message) ?></div>
    <?php endif; ?>

    <?php if ($error): ?>
        <div class="message error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <div class="card">
        <h2>Column Status</h2>
        <p>
            <strong>alias:</strong>
            <span class="status <?= $has_alias ? 'ok' : 'missing' ?>">
                <?= $has_alias ? 'EXISTS' : 'MISSING' ?>
            </span>
        </p>
        <p>
            <strong>alias_updated_at:</strong>
            <span class="status <?= $has_alias_updated ? 'ok' : 'missing' ?>">
                <?= $has_alias_updated ? 'EXISTS' : 'MISSING' ?>
            </span>
        </p>

        <?php if (!$has_alias || !$has_alias_updated): ?>
        <form method="POST" style="margin-top: 16px;">
            <input type="hidden" name="action" value="add_columns">
            <button type="submit" class="btn btn-primary">Add Missing Columns</button>
        </form>
        <?php else: ?>
        <p style="color: #22c55e; margin-top: 16px;">All columns present - name editing should work!</p>
        <?php endif; ?>
    </div>

    <div class="card">
        <h2>Device Status</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>UUID</th>
                    <th>Status</th>
                    <th>Issues</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($devices as $d): ?>
                <tr>
                    <td><?= $d['id'] ?></td>
                    <td><?= htmlspecialchars($d['name']) ?></td>
                    <td style="font-family: monospace;"><?= substr($d['device_uuid'], 0, 8) ?>...</td>
                    <td>
                        <span class="status <?= $d['has_issues'] ? 'issues' : 'ok' ?>">
                            <?= $d['has_issues'] ? 'HAS ISSUES' : 'OK' ?>
                        </span>
                    </td>
                    <td>
                        <?php if ($d['has_issues'] && $d['issues_json']): ?>
                            <pre><?= htmlspecialchars($d['issues_json']) ?></pre>
                        <?php elseif ($d['alarms_critical'] > 0): ?>
                            <?= $d['alarms_critical'] ?> critical alarms
                        <?php elseif ($d['controllers_offline'] > 0): ?>
                            <?= $d['controllers_offline'] ?> controllers offline
                        <?php else: ?>
                            -
                        <?php endif; ?>
                    </td>
                    <td>
                        <?php if ($d['has_issues']): ?>
                        <form method="POST" style="display: inline;">
                            <input type="hidden" name="action" value="clear_issues">
                            <input type="hidden" name="device_id" value="<?= $d['id'] ?>">
                            <button type="submit" class="btn btn-danger btn-sm">Clear Issues</button>
                        </form>
                        <?php endif; ?>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <p><a href="index.php">Back to Dashboard</a> | <a href="queue_test.php">Queue Test Question</a></p>
</body>
</html>
