<?php
/**
 * Admin UI for issuing single-use per-device bootstrap codes.
 *
 * Replaces the shared-secret provisioning flow: an admin generates a code,
 * shares it with the field operator, they enter it once on a Pi's first-boot
 * setup page. The Pi exchanges the code for a long-lived API key via
 * provision.php (which marks the code used so it cannot be replayed).
 */

declare(strict_types=1);

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();

// Ensure table exists (idempotent).
$pdo->exec("CREATE TABLE IF NOT EXISTS bootstrap_codes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code_hash CHAR(64) NOT NULL UNIQUE,
    device_uuid VARCHAR(64) NULL,
    label VARCHAR(200) NOT NULL,
    issued_by_admin_id INT NULL,
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    used_at TIMESTAMP NULL,
    used_ip VARCHAR(64) NULL,
    revoked_at TIMESTAMP NULL,
    revoked_reason TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

$newCode = null;
$flash = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';
    if ($action === 'issue') {
        $label = trim($_POST['label'] ?? '');
        $expiresHours = (int)($_POST['expires_hours'] ?? 72);
        if ($label === '') {
            $flash = ['err', 'Label required'];
        } else {
            // Generate a 24-char human-friendly code (URL-safe base32-ish).
            $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
            $plain = '';
            for ($i = 0; $i < 24; $i++) {
                $plain .= $alphabet[random_int(0, strlen($alphabet) - 1)];
                if ($i > 0 && ($i + 1) % 6 === 0 && $i < 23) {
                    $plain .= '-';
                }
            }
            $hash = hash('sha256', $plain);
            $expiresAt = $expiresHours > 0
                ? date('Y-m-d H:i:s', time() + $expiresHours * 3600)
                : null;
            $stmt = $pdo->prepare("
                INSERT INTO bootstrap_codes
                    (code_hash, label, issued_by_admin_id, expires_at)
                VALUES (?, ?, ?, ?)
            ");
            $stmt->execute([
                $hash, $label,
                (int)($_SESSION['admin_id'] ?? 0),
                $expiresAt,
            ]);
            $newCode = $plain;
            $flash = ['ok', "Code issued (label: " . htmlspecialchars($label) . "). Shown once only."];
        }
    } elseif ($action === 'revoke') {
        $id = (int)($_POST['id'] ?? 0);
        $reason = trim($_POST['reason'] ?? 'revoked by admin');
        if ($id > 0) {
            $stmt = $pdo->prepare("
                UPDATE bootstrap_codes
                SET revoked_at = NOW(), revoked_reason = ?
                WHERE id = ? AND revoked_at IS NULL
            ");
            $stmt->execute([$reason, $id]);
            $flash = ['ok', 'Code revoked'];
        }
    }
}

$codes = $pdo->query("
    SELECT id, label, device_uuid, issued_at, expires_at, used_at, used_ip, revoked_at, revoked_reason
    FROM bootstrap_codes
    ORDER BY issued_at DESC
    LIMIT 100
")->fetchAll(PDO::FETCH_ASSOC);

function status_of(array $row): string {
    if ($row['revoked_at']) return 'revoked';
    if ($row['used_at']) return 'used';
    if ($row['expires_at'] && strtotime($row['expires_at']) < time()) return 'expired';
    return 'pending';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bootstrap Codes - PoolAIssistant Admin</title>
    <style>
        body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0f172a; color: #f1f5f9; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 1.5rem; margin-bottom: 1rem; }
        h1 span { color: #3b82f6; }
        nav { margin-bottom: 1.5rem; }
        nav a { color: #94a3b8; margin-right: 12px; text-decoration: none; font-size: 0.9rem; }
        nav a:hover { color: #f1f5f9; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
        .flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; font-size: 0.9rem; }
        .flash.ok { background: rgba(34,197,94,0.15); color: #86efac; }
        .flash.err { background: rgba(239,68,68,0.15); color: #fca5a5; }
        .code-reveal {
            background: #0f172a; border: 2px solid #f59e0b; border-radius: 10px;
            padding: 20px; margin-bottom: 20px; text-align: center;
        }
        .code-reveal .val {
            font-family: SF Mono, Consolas, monospace; font-size: 1.75rem;
            letter-spacing: 0.08em; margin: 12px 0; user-select: all; color: #fbbf24;
        }
        .code-reveal .note { font-size: 0.85rem; color: #fca5a5; }
        form.inline { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
        label { display: block; font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px; }
        input, select {
            padding: 8px 12px; border-radius: 6px; border: 1px solid #475569;
            background: #0f172a; color: #f1f5f9; font-size: 0.9rem; font-family: inherit;
        }
        button {
            padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer;
            font-size: 0.9rem; font-family: inherit; font-weight: 600;
        }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-danger { background: #ef4444; color: white; }
        table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
        th { text-align: left; padding: 10px; background: #334155; color: #94a3b8;
             font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
        td { padding: 10px; border-top: 1px solid #334155; }
        .status { font-size: 0.75rem; font-weight: 600; padding: 3px 8px; border-radius: 999px; }
        .status.pending  { background: rgba(245,158,11,0.2); color: #fbbf24; }
        .status.used     { background: rgba(34,197,94,0.2); color: #86efac; }
        .status.expired  { background: rgba(148,163,184,0.2); color: #cbd5e1; }
        .status.revoked  { background: rgba(239,68,68,0.2); color: #fca5a5; }
    </style>
</head>
<body>
<div class="container">
    <h1>Pool<span>AI</span> &middot; Bootstrap Codes</h1>
    <nav>
        <a href="/admin/">Devices</a>
        <a href="/admin/clients.php">Clients</a>
        <a href="/admin/ai_dashboard.php">AI</a>
        <a href="/admin/bootstrap_codes.php"><strong>Bootstrap codes</strong></a>
    </nav>

    <?php if ($flash): ?>
        <div class="flash <?= $flash[0] ?>"><?= $flash[1] ?></div>
    <?php endif; ?>

    <?php if ($newCode): ?>
        <div class="code-reveal">
            <div>This is the only time this code will be shown.</div>
            <div class="val"><?= htmlspecialchars($newCode) ?></div>
            <div class="note">Share with the on-site operator. Do not write down centrally.</div>
        </div>
    <?php endif; ?>

    <div class="card">
        <h2 style="font-size: 1rem; margin-bottom: 12px;">Issue a new code</h2>
        <form method="POST" class="inline">
            <input type="hidden" name="action" value="issue">
            <div>
                <label for="label">Label</label>
                <input type="text" id="label" name="label" required
                       placeholder="e.g. Henley Leisure - Pool 2 replacement">
            </div>
            <div>
                <label for="expires_hours">Expires in (hours, 0 = never)</label>
                <input type="number" id="expires_hours" name="expires_hours" value="72" min="0">
            </div>
            <button type="submit" class="btn-primary">Issue code</button>
        </form>
    </div>

    <div class="card">
        <h2 style="font-size: 1rem; margin-bottom: 12px;">Recent codes (100 most recent)</h2>
        <table>
            <thead>
                <tr>
                    <th>Label</th>
                    <th>Status</th>
                    <th>Issued</th>
                    <th>Expires</th>
                    <th>Used</th>
                    <th>Device</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($codes as $c):
                $status = status_of($c);
            ?>
                <tr>
                    <td><?= htmlspecialchars($c['label']) ?></td>
                    <td><span class="status <?= $status ?>"><?= $status ?></span></td>
                    <td><?= htmlspecialchars($c['issued_at']) ?></td>
                    <td><?= htmlspecialchars($c['expires_at'] ?? '-') ?></td>
                    <td>
                        <?= htmlspecialchars($c['used_at'] ?? '-') ?>
                        <?php if ($c['used_ip']): ?>
                            <br><small style="color: #94a3b8;">from <?= htmlspecialchars($c['used_ip']) ?></small>
                        <?php endif; ?>
                    </td>
                    <td style="font-family: monospace; font-size: 0.8rem;">
                        <?= htmlspecialchars(substr($c['device_uuid'] ?? '-', 0, 12)) ?><?= $c['device_uuid'] ? '&hellip;' : '' ?>
                    </td>
                    <td>
                        <?php if ($status === 'pending'): ?>
                            <form method="POST" style="display:inline"
                                  onsubmit="return confirm('Revoke this code?')">
                                <input type="hidden" name="action" value="revoke">
                                <input type="hidden" name="id" value="<?= (int)$c['id'] ?>">
                                <button type="submit" class="btn-danger">Revoke</button>
                            </form>
                        <?php endif; ?>
                    </td>
                </tr>
            <?php endforeach; ?>
            <?php if (empty($codes)): ?>
                <tr><td colspan="7" style="text-align:center; color:#94a3b8; padding:30px;">
                    No codes issued yet.
                </td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>
</body>
</html>
