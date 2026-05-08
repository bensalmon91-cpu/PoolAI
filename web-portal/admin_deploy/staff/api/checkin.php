<?php
/**
 * Staff PWA - Check-ins
 *
 * GET  /staff/api/checkin.php              - list recent check-ins
 * POST /staff/api/checkin.php              - create a check-in
 *        body: { status: 'ok'|'attention'|'issue', note?: string }
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
requireAdmin();

$pdo = db();
$method = $_SERVER['REQUEST_METHOD'];

// Make sure the check-ins table exists — self-provision on first use so staff
// don't have to run a separate migration. This is idempotent.
try {
    $pdo->exec("CREATE TABLE IF NOT EXISTS staff_checkins (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        admin_id INT NOT NULL,
        admin_username VARCHAR(100) NOT NULL,
        status ENUM('ok','attention','issue') NOT NULL DEFAULT 'ok',
        note TEXT,
        devices_online INT DEFAULT NULL,
        devices_offline INT DEFAULT NULL,
        devices_with_issues INT DEFAULT NULL,
        pending_suggestions INT DEFAULT NULL,
        flagged_responses INT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_admin (admin_id),
        INDEX idx_created (created_at),
        INDEX idx_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
} catch (PDOException $e) {
    errorResponse('Database error: could not create staff_checkins', 500);
}

try {
    if ($method === 'GET') {
        $limit = min((int)($_GET['limit'] ?? 30), 200);
        $stmt = $pdo->prepare("
            SELECT id, admin_username, status, note,
                   devices_online, devices_offline, devices_with_issues,
                   pending_suggestions, flagged_responses, created_at
            FROM staff_checkins
            ORDER BY created_at DESC
            LIMIT ?
        ");
        $stmt->bindValue(1, $limit, PDO::PARAM_INT);
        $stmt->execute();
        $checkins = $stmt->fetchAll(PDO::FETCH_ASSOC);
        successResponse(['checkins' => $checkins]);
    }

    if ($method === 'POST') {
        $input = getJsonInput();
        $status = $input['status'] ?? 'ok';
        $valid = ['ok', 'attention', 'issue'];
        if (!in_array($status, $valid, true)) {
            errorResponse('Invalid status; must be ok/attention/issue');
        }
        $note = isset($input['note']) ? trim((string)$input['note']) : '';
        if (strlen($note) > 2000) {
            errorResponse('Note too long (max 2000 chars)');
        }

        // Snapshot a small amount of context with the check-in so the log is
        // useful even if fleet state changes later.
        $online = $offline = $with_issues = null;
        try {
            $row = $pdo->query("
                SELECT
                  SUM(CASE WHEN d.last_seen IS NOT NULL AND TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) < 20 THEN 1 ELSE 0 END) AS online,
                  SUM(CASE WHEN d.last_seen IS NULL OR TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) >= 20 THEN 1 ELSE 0 END) AS offline,
                  SUM(CASE WHEN h.has_issues = 1 THEN 1 ELSE 0 END) AS with_issues
                FROM pi_devices d
                LEFT JOIN (
                    SELECT h1.device_id, h1.has_issues
                    FROM device_health h1
                    INNER JOIN (
                        SELECT device_id, MAX(ts) AS max_ts
                        FROM device_health GROUP BY device_id
                    ) h2 ON h1.device_id = h2.device_id AND h1.ts = h2.max_ts
                ) h ON d.id = h.device_id
                WHERE d.is_active = 1
            ")->fetch(PDO::FETCH_ASSOC);
            if ($row) {
                $online = (int)$row['online'];
                $offline = (int)$row['offline'];
                $with_issues = (int)$row['with_issues'];
            }
        } catch (PDOException $e) { /* ignore snapshot errors */ }

        $pending = null;
        $flagged = null;
        try {
            $pending = (int)$pdo->query("
                SELECT COUNT(*) FROM ai_suggestions
                WHERE status IN ('pending','delivered','read')
            ")->fetchColumn();
            $flagged = (int)$pdo->query("
                SELECT COUNT(*) FROM ai_responses WHERE flagged = 1
            ")->fetchColumn();
        } catch (PDOException $e) { /* AI tables may not exist */ }

        $stmt = $pdo->prepare("
            INSERT INTO staff_checkins
                (admin_id, admin_username, status, note,
                 devices_online, devices_offline, devices_with_issues,
                 pending_suggestions, flagged_responses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ");
        $stmt->execute([
            (int)($_SESSION['admin_id'] ?? 0),
            (string)($_SESSION['admin_username'] ?? 'staff'),
            $status,
            $note !== '' ? $note : null,
            $online, $offline, $with_issues,
            $pending, $flagged,
        ]);

        successResponse(['id' => (int)$pdo->lastInsertId()], 'Check-in recorded');
    }

    errorResponse('Method not allowed', 405);
} catch (PDOException $e) {
    errorResponse('Database error', 500);
}
