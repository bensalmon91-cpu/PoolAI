<?php
/**
 * Admin audit viewer.
 *
 * Two tabs:
 *   - events:   rich semantic log from the event_log table (default)
 *               — covers admin actions, customer-portal events, Pi↔cloud
 *                 traffic, system events.
 *   - http:     flat-file tail of admin_audit.log (every admin HTTP request)
 *               — low-level diagnostic backup.
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$tab = $_GET['tab'] ?? 'events';
if (!in_array($tab, ['events', 'http'], true)) $tab = 'events';

// Self-bootstrap: ensure event_log exists on first viewer load. Idempotent.
// Schema source-of-truth lives in schema_event_log.sql.
$EVENT_LOG_DDL = "CREATE TABLE IF NOT EXISTS event_log (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tier            ENUM('admin','portal','device','system') NOT NULL,
    actor_type      ENUM('admin','user','device','system','anonymous') NOT NULL,
    actor_id        VARCHAR(64) NULL,
    action          VARCHAR(64) NOT NULL,
    target_type     VARCHAR(32) NULL,
    target_id       VARCHAR(64) NULL,
    result          ENUM('ok','fail','denied') NOT NULL DEFAULT 'ok',
    details_json    JSON NULL,
    ip_address      VARCHAR(45) NULL,
    user_agent      VARCHAR(255) NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created (created_at),
    INDEX idx_tier_action (tier, action, created_at),
    INDEX idx_actor (actor_type, actor_id, created_at),
    INDEX idx_target (target_type, target_id, created_at),
    INDEX idx_result (result, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4";
try {
    db()->query($EVENT_LOG_DDL);
} catch (Throwable $e) {
    // Don't block the viewer if migration fails - the table-missing
    // error path further down already surfaces this clearly.
}

// ---------------------------------------------------------------------------
// Events tab (event_log table)
// ---------------------------------------------------------------------------
$ev_tier      = trim($_GET['tier']    ?? '');
$ev_actor     = trim($_GET['actor']   ?? '');
$ev_action    = trim($_GET['action']  ?? '');
$ev_target    = trim($_GET['target']  ?? '');
$ev_result    = trim($_GET['result']  ?? '');
$ev_since_h   = (int)($_GET['since_hours'] ?? 24);
if ($ev_since_h < 1)    $ev_since_h = 1;
if ($ev_since_h > 8760) $ev_since_h = 8760;  // 1 year

$ev_limit = (int)($_GET['limit'] ?? 200);
if ($ev_limit < 10)   $ev_limit = 10;
if ($ev_limit > 1000) $ev_limit = 1000;

$events = [];
$events_total = 0;
$events_error = null;

if ($tab === 'events') {
    try {
        $pdo = db();
        $where = ['created_at > (NOW() - INTERVAL :h HOUR)'];
        $params = [':h' => $ev_since_h];
        if ($ev_tier !== '')   { $where[] = 'tier = :tier';      $params[':tier']   = $ev_tier; }
        if ($ev_actor !== '')  { $where[] = 'actor_id LIKE :ac'; $params[':ac']     = '%' . $ev_actor . '%'; }
        if ($ev_action !== '') { $where[] = 'action LIKE :act';  $params[':act']    = $ev_action . '%'; }
        if ($ev_target !== ''){ $where[] = '(target_type LIKE :tt OR target_id LIKE :ti)'; $params[':tt'] = '%' . $ev_target . '%'; $params[':ti'] = '%' . $ev_target . '%'; }
        if ($ev_result !== '') { $where[] = 'result = :res';     $params[':res']    = $ev_result; }
        $whereSql = implode(' AND ', $where);

        $countStmt = $pdo->prepare("SELECT COUNT(*) AS n FROM event_log WHERE $whereSql");
        $countStmt->execute($params);
        $events_total = (int)$countStmt->fetch()['n'];

        $stmt = $pdo->prepare("
            SELECT id, tier, actor_type, actor_id, action, target_type, target_id,
                   result, details_json, ip_address, user_agent, created_at
            FROM event_log
            WHERE $whereSql
            ORDER BY created_at DESC, id DESC
            LIMIT $ev_limit
        ");
        $stmt->execute($params);
        $events = $stmt->fetchAll(PDO::FETCH_ASSOC);
    } catch (Throwable $e) {
        $events_error = $e->getMessage();
    }
}

// ---------------------------------------------------------------------------
// HTTP tab (flat-file admin_audit.log)
// ---------------------------------------------------------------------------
$LOG_PATH = __DIR__ . '/../admin_audit.log';
$http_limit = (int)($_GET['limit'] ?? 200);
if ($http_limit < 10)   $http_limit = 10;
if ($http_limit > 5000) $http_limit = 5000;
$http_user   = trim($_GET['user'] ?? '');
$http_status = trim($_GET['status'] ?? '');
$http_uri    = trim($_GET['uri'] ?? '');

function tail_lines(string $path, int $n): array {
    if (!is_file($path) || !is_readable($path)) return [];
    $size = filesize($path);
    if ($size === 0) return [];
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

$http_rows = [];
$log_size  = 0;
if ($tab === 'http') {
    $raw = tail_lines($LOG_PATH, $http_limit * 3);
    foreach ($raw as $line) {
        $parts = explode("\t", $line);
        if (count($parts) < 7) continue;
        [$ts, $user, $status, $method, $uri, $dur, $ip] = $parts;
        if ($http_user   !== '' && stripos($user, $http_user) === false)   continue;
        if ($http_status !== '' && (string)$status !== $http_status)        continue;
        if ($http_uri    !== '' && stripos($uri, $http_uri) === false)      continue;
        $http_rows[] = compact('ts','user','status','method','uri','dur','ip');
    }
    $http_rows = array_slice(array_reverse($http_rows), 0, $http_limit);
    $log_size  = is_file($LOG_PATH) ? filesize($LOG_PATH) : 0;
}

function tier_color(string $t): string {
    return [
        'admin'  => '#fbbf24',
        'portal' => '#60a5fa',
        'device' => '#34d399',
        'system' => '#a78bfa',
    ][$t] ?? '#94a3b8';
}
function result_class(string $r): string {
    return [
        'ok'     => 'pill pill-ok',
        'fail'   => 'pill pill-fail',
        'denied' => 'pill pill-denied',
    ][$r] ?? 'pill';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Admin Audit - PoolAIssistant</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f1f5f9; margin: 0; padding: 20px; }
        h1 { margin: 0 0 4px; }
        .meta { color: #94a3b8; font-size: 13px; margin-bottom: 16px; }
        nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
        nav a { background: #334155; color: #f1f5f9; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 13px; }
        nav a:hover { background: #475569; }
        .tabs { display: flex; gap: 4px; margin-bottom: 0; border-bottom: 1px solid #334155; }
        .tabs a { padding: 8px 16px; color: #94a3b8; text-decoration: none; border-bottom: 2px solid transparent; font-size: 14px; }
        .tabs a.active { color: #f1f5f9; border-bottom-color: #3b82f6; font-weight: 600; }
        .tabs a:hover { color: #f1f5f9; }
        form { background: #1e293b; padding: 12px; border-radius: 0 6px 6px 6px; margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        form input, form select { background: #0f172a; border: 1px solid #475569; color: #f1f5f9; padding: 6px 10px; border-radius: 4px; font-size: 13px; }
        form button { background: #3b82f6; color: white; border: 0; padding: 6px 14px; border-radius: 4px; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 6px; overflow: hidden; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; vertical-align: top; }
        th { background: #0f172a; color: #94a3b8; font-weight: 600; }
        tr:hover { background: #2a3a52; }
        .ts { color: #94a3b8; white-space: nowrap; font-family: ui-monospace, monospace; font-size: 12px; }
        .user { color: #60a5fa; }
        .mono { font-family: ui-monospace, monospace; }
        .tier-pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; color: #0f172a; }
        .pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
        .pill-ok     { background: #064e3b; color: #6ee7b7; }
        .pill-fail   { background: #7f1d1d; color: #fca5a5; }
        .pill-denied { background: #78350f; color: #fcd34d; }
        .details-toggle { background: none; border: 0; color: #60a5fa; cursor: pointer; padding: 0; font-size: 12px; }
        .details-pre { background: #0f172a; padding: 8px; border-radius: 4px; margin-top: 6px; font-size: 11px; max-width: 600px; overflow: auto; }
        .method { font-weight: 600; }
        .method-GET  { color: #34d399; }
        .method-POST { color: #fbbf24; }
        .method-DELETE { color: #f87171; }
        .method-PUT  { color: #fbbf24; }
        .status { font-weight: 600; padding: 2px 6px; border-radius: 3px; font-family: ui-monospace, monospace; }
        .status-2xx { background: #064e3b; color: #6ee7b7; }
        .status-3xx { background: #1e3a8a; color: #93c5fd; }
        .status-4xx { background: #78350f; color: #fcd34d; }
        .status-5xx { background: #7f1d1d; color: #fca5a5; }
        .uri { font-family: ui-monospace, monospace; word-break: break-all; }
        .empty { padding: 40px; text-align: center; color: #94a3b8; }
        .err { background: #7f1d1d; color: #fecaca; padding: 12px; border-radius: 6px; margin-bottom: 16px; }
    </style>
</head>
<body>
    <h1>Audit log</h1>
    <div class="meta">
        <?php if ($tab === 'events'): ?>
            Showing <?= count($events) ?> of <?= number_format($events_total) ?> matching event(s) from the last <?= $ev_since_h ?> hour(s).
        <?php else: ?>
            Showing the most recent <?= count($http_rows) ?> HTTP request(s)
            from <?= htmlspecialchars(basename($LOG_PATH)) ?>
            (<?= number_format($log_size) ?> bytes total).
        <?php endif ?>
    </div>

    <nav>
        <a href="index.php">&larr; Devices</a>
        <a href="clients.php">Clients</a>
        <a href="bootstrap_codes.php">Bootstrap codes</a>
        <a href="ai_dashboard.php">AI</a>
        <a href="audit.php?tab=<?= htmlspecialchars($tab) ?>">Audit (refresh)</a>
        <a href="logout.php">Logout</a>
    </nav>

    <div class="tabs">
        <a href="?tab=events" class="<?= $tab === 'events' ? 'active' : '' ?>">Events</a>
        <a href="?tab=http"   class="<?= $tab === 'http'   ? 'active' : '' ?>">HTTP requests</a>
    </div>

    <?php if ($events_error): ?>
        <div class="err">
            event_log query failed: <?= htmlspecialchars($events_error) ?>
            <br><small>If the table doesn't exist yet, run <code>web-portal/php_deploy/database/schema_event_log.sql</code> against the database.</small>
        </div>
    <?php endif ?>

    <?php if ($tab === 'events'): ?>
        <form method="get">
            <input type="hidden" name="tab" value="events">
            <label>Tier:
                <select name="tier">
                    <option value="">all</option>
                    <?php foreach (['admin','portal','device','system'] as $t): ?>
                        <option value="<?= $t ?>" <?= $ev_tier === $t ? 'selected' : '' ?>><?= $t ?></option>
                    <?php endforeach ?>
                </select>
            </label>
            <label>Actor (id contains): <input name="actor" value="<?= htmlspecialchars($ev_actor) ?>" placeholder="bensalmon, 42, pi-xxx" size="14"></label>
            <label>Action (starts with): <input name="action" value="<?= htmlspecialchars($ev_action) ?>" placeholder="client., device., auth." size="14"></label>
            <label>Target (id or type): <input name="target" value="<?= htmlspecialchars($ev_target) ?>" placeholder="device, 7" size="10"></label>
            <label>Result:
                <select name="result">
                    <option value="">any</option>
                    <option value="ok"     <?= $ev_result === 'ok'     ? 'selected' : '' ?>>ok</option>
                    <option value="fail"   <?= $ev_result === 'fail'   ? 'selected' : '' ?>>fail</option>
                    <option value="denied" <?= $ev_result === 'denied' ? 'selected' : '' ?>>denied</option>
                </select>
            </label>
            <label>Since (hours): <input name="since_hours" type="number" min="1" max="8760" value="<?= $ev_since_h ?>" size="5"></label>
            <label>Limit: <input name="limit" type="number" min="10" max="1000" value="<?= $ev_limit ?>" size="5"></label>
            <button type="submit">Apply</button>
            <a href="audit.php?tab=events" style="color: #94a3b8; font-size: 13px; margin-left: 8px;">Clear filters</a>
        </form>

        <?php if (empty($events) && !$events_error): ?>
            <div class="empty">
                No events matched. Try widening the time range or clearing filters.
            </div>
        <?php elseif (!$events_error): ?>
            <table>
                <thead>
                    <tr>
                        <th>Time (UTC)</th>
                        <th>Tier</th>
                        <th>Actor</th>
                        <th>Action</th>
                        <th>Target</th>
                        <th>Result</th>
                        <th>IP</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($events as $e): ?>
                        <tr>
                            <td class="ts"><?= htmlspecialchars($e['created_at']) ?></td>
                            <td><span class="tier-pill" style="background: <?= tier_color($e['tier']) ?>"><?= htmlspecialchars($e['tier']) ?></span></td>
                            <td class="mono">
                                <?= htmlspecialchars($e['actor_type']) ?><br>
                                <span class="user"><?= htmlspecialchars((string)$e['actor_id']) ?></span>
                            </td>
                            <td class="mono"><?= htmlspecialchars($e['action']) ?></td>
                            <td class="mono">
                                <?= htmlspecialchars((string)$e['target_type']) ?>
                                <?php if ($e['target_id']): ?>
                                    <br><span style="color:#94a3b8"><?= htmlspecialchars($e['target_id']) ?></span>
                                <?php endif ?>
                            </td>
                            <td><span class="<?= result_class($e['result']) ?>"><?= htmlspecialchars($e['result']) ?></span></td>
                            <td class="mono" style="color: #94a3b8"><?= htmlspecialchars((string)$e['ip_address']) ?></td>
                            <td>
                                <?php if ($e['details_json']): ?>
                                    <button class="details-toggle" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'block' ? 'none' : 'block'">show</button>
                                    <pre class="details-pre" style="display:none"><?= htmlspecialchars(json_encode(json_decode($e['details_json']), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) ?></pre>
                                <?php endif ?>
                            </td>
                        </tr>
                    <?php endforeach ?>
                </tbody>
            </table>
        <?php endif ?>

    <?php else: /* HTTP tab */ ?>
        <form method="get">
            <input type="hidden" name="tab" value="http">
            <label>User: <input name="user" value="<?= htmlspecialchars($http_user) ?>" placeholder="username" size="14"></label>
            <label>Status: <input name="status" value="<?= htmlspecialchars($http_status) ?>" placeholder="200, 500..." size="6"></label>
            <label>URI contains: <input name="uri" value="<?= htmlspecialchars($http_uri) ?>" placeholder="device_alias" size="20"></label>
            <label>Limit: <input name="limit" value="<?= $http_limit ?>" size="5" type="number" min="10" max="5000"></label>
            <button type="submit">Apply</button>
            <a href="audit.php?tab=http" style="color: #94a3b8; font-size: 13px; margin-left: 8px;">Clear filters</a>
        </form>

        <?php if (empty($http_rows)): ?>
            <div class="empty">
                No log entries yet (or no entries matched your filter).
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
                        <th>IP</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($http_rows as $r): ?>
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
                            <td class="mono" style="color:#94a3b8"><?= htmlspecialchars($r['dur']) ?> ms</td>
                            <td class="mono" style="color:#94a3b8"><?= htmlspecialchars($r['ip']) ?></td>
                        </tr>
                    <?php endforeach ?>
                </tbody>
            </table>
        <?php endif ?>
    <?php endif ?>
</body>
</html>
