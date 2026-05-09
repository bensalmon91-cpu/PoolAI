<?php
/**
 * Admin audit log viewer.
 * Reads the last N lines of admin_audit.log and renders them as a table.
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$LOG_PATH = __DIR__ . '/../admin_audit.log';
$LIMIT = (int) ($_GET['limit'] ?? 200);
if ($LIMIT < 10) $LIMIT = 10;
if ($LIMIT > 5000) $LIMIT = 5000;

$filter_user   = trim($_GET['user'] ?? '');
$filter_status = trim($_GET['status'] ?? '');
$filter_uri    = trim($_GET['uri'] ?? '');

function tail_lines(string $path, int $n): array {
    if (!is_file($path) || !is_readable($path)) return [];
    $size = filesize($path);
    if ($size === 0) return [];
    // Read trailing chunk; for n=200 even verbose lines stay under 256KB.
    $chunk = min($size, max(64 * 1024, $n * 600));
    $fh = fopen($path, 'rb');
    if (!$fh) return [];
    fseek($fh, -$chunk, SEEK_END);
    $data = fread($fh, $chunk);
    fclose($fh);
    $lines = preg_split("/\r?\n/", $data);
    if (count($lines) > $n + 1) {
        $lines = array_slice($lines, -($n + 1));
    }
    return array_values(array_filter($lines, fn($l) => trim($l) !== ''));
}

$rows_raw = tail_lines($LOG_PATH, $LIMIT * 3);  // grab extra for filter slack
$rows = [];
foreach ($rows_raw as $line) {
    $parts = explode("\t", $line);
    if (count($parts) < 7) continue;
    [$ts, $user, $status, $method, $uri, $dur, $ip] = $parts;
    if ($filter_user   !== '' && stripos($user, $filter_user) === false)   continue;
    if ($filter_status !== '' && (string)$status !== $filter_status)        continue;
    if ($filter_uri    !== '' && stripos($uri, $filter_uri) === false)      continue;
    $rows[] = compact('ts','user','status','method','uri','dur','ip');
}
$rows = array_slice(array_reverse($rows), 0, $LIMIT);  // newest first
$log_size = is_file($LOG_PATH) ? filesize($LOG_PATH) : 0;
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Admin Audit Log - PoolAIssistant</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f1f5f9; margin: 0; padding: 20px; }
        h1 { margin: 0 0 4px; }
        .meta { color: #94a3b8; font-size: 13px; margin-bottom: 16px; }
        nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
        nav a { background: #334155; color: #f1f5f9; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 13px; }
        nav a:hover { background: #475569; }
        form { background: #1e293b; padding: 12px; border-radius: 6px; margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        form input, form select { background: #0f172a; border: 1px solid #475569; color: #f1f5f9; padding: 6px 10px; border-radius: 4px; font-size: 13px; }
        form button { background: #3b82f6; color: white; border: 0; padding: 6px 14px; border-radius: 4px; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 6px; overflow: hidden; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; }
        th { background: #0f172a; color: #94a3b8; font-weight: 600; }
        tr:hover { background: #2a3a52; }
        .ts { color: #94a3b8; white-space: nowrap; font-family: ui-monospace, monospace; font-size: 12px; }
        .user { color: #60a5fa; }
        .method { font-weight: 600; }
        .method-GET    { color: #34d399; }
        .method-POST   { color: #fbbf24; }
        .method-DELETE { color: #f87171; }
        .method-PUT    { color: #fbbf24; }
        .status { font-weight: 600; padding: 2px 6px; border-radius: 3px; font-family: ui-monospace, monospace; }
        .status-2xx { background: #064e3b; color: #6ee7b7; }
        .status-3xx { background: #1e3a8a; color: #93c5fd; }
        .status-4xx { background: #78350f; color: #fcd34d; }
        .status-5xx { background: #7f1d1d; color: #fca5a5; }
        .uri { font-family: ui-monospace, monospace; word-break: break-all; }
        .dur, .ip { color: #94a3b8; font-family: ui-monospace, monospace; }
        .empty { padding: 40px; text-align: center; color: #94a3b8; }
    </style>
</head>
<body>
    <h1>Admin audit log</h1>
    <div class="meta">
        Showing the most recent <?= count($rows) ?> request(s)
        from <?= htmlspecialchars(basename($LOG_PATH)) ?>
        (<?= number_format($log_size) ?> bytes total).
    </div>

    <nav>
        <a href="index.php">&larr; Devices</a>
        <a href="clients.php">Clients</a>
        <a href="bootstrap_codes.php">Bootstrap codes</a>
        <a href="ai_dashboard.php">AI</a>
        <a href="audit.php">Audit (refresh)</a>
        <a href="logout.php">Logout</a>
    </nav>

    <form method="get">
        <label>User: <input name="user" value="<?= htmlspecialchars($filter_user) ?>" placeholder="username" size="14"></label>
        <label>Status: <input name="status" value="<?= htmlspecialchars($filter_status) ?>" placeholder="200, 500..." size="6"></label>
        <label>URI contains: <input name="uri" value="<?= htmlspecialchars($filter_uri) ?>" placeholder="device_alias" size="20"></label>
        <label>Limit: <input name="limit" value="<?= $LIMIT ?>" size="5" type="number" min="10" max="5000"></label>
        <button type="submit">Apply</button>
        <a href="audit.php" style="color: #94a3b8; font-size: 13px; margin-left: 8px;">Clear filters</a>
    </form>

    <?php if (empty($rows)): ?>
        <div class="empty">
            No log entries yet (or no entries matched your filter).
            <br>Click around the admin and refresh this page to see activity.
        </div>
    <?php else: ?>
        <table>
            <thead>
                <tr>
                    <th>Time (UTC)</th>
                    <th>User</th>
                    <th>Method</th>
                    <th>URI</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th class="hide-mobile">IP</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($rows as $r): ?>
                    <?php
                        $statusClass = 'status-' . (substr((string)$r['status'], 0, 1) ?: '0') . 'xx';
                        $methodClass = 'method-' . htmlspecialchars($r['method']);
                    ?>
                    <tr>
                        <td class="ts"><?= htmlspecialchars($r['ts']) ?></td>
                        <td class="user"><?= htmlspecialchars($r['user']) ?></td>
                        <td class="method <?= $methodClass ?>"><?= htmlspecialchars($r['method']) ?></td>
                        <td class="uri"><?= htmlspecialchars($r['uri']) ?></td>
                        <td><span class="status <?= $statusClass ?>"><?= htmlspecialchars($r['status']) ?></span></td>
                        <td class="dur"><?= htmlspecialchars($r['dur']) ?> ms</td>
                        <td class="ip hide-mobile"><?= htmlspecialchars($r['ip']) ?></td>
                    </tr>
                <?php endforeach ?>
            </tbody>
        </table>
    <?php endif ?>
</body>
</html>
