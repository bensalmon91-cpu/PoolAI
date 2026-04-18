<?php
/**
 * Staff PWA - Dashboard summary
 * GET /staff/api/dashboard.php
 *
 * Returns fleet health + AI governance counts used by the PWA home screen.
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
requireAdmin();
requireMethod('GET');

$pdo = db();

try {
    // Device fleet (mirrors admin/index.php logic)
    $devices = $pdo->query("
        SELECT
            d.id, d.device_uuid, d.name, d.alias, d.last_seen, d.is_active,
            h.has_issues, h.alarms_critical, h.alarms_total,
            h.controllers_offline, h.software_version, h.ts AS health_ts
        FROM pi_devices d
        LEFT JOIN (
            SELECT h1.*
            FROM device_health h1
            INNER JOIN (
                SELECT device_id, MAX(ts) AS max_ts
                FROM device_health
                GROUP BY device_id
            ) h2 ON h1.device_id = h2.device_id AND h1.ts = h2.max_ts
        ) h ON d.id = h.device_id
        WHERE d.is_active = 1
        ORDER BY d.name, d.id
    ")->fetchAll(PDO::FETCH_ASSOC);

    $now = time();
    $online = 0; $offline = 0; $with_issues = 0; $critical = 0;
    $device_list = [];

    foreach ($devices as $d) {
        $last = $d['last_seen'] ? strtotime($d['last_seen']) : null;
        $minutes_ago = $last !== null ? (int)round(($now - $last) / 60) : null;
        $is_online = $minutes_ago !== null && $minutes_ago < 20;

        if ($is_online) { $online++; } else { $offline++; }
        if ((int)($d['has_issues'] ?? 0) === 1) { $with_issues++; }
        $critical += (int)($d['alarms_critical'] ?? 0);

        $device_list[] = [
            'id' => (int)$d['id'],
            'name' => $d['alias'] ?: ($d['name'] ?: ('Device ' . $d['id'])),
            'uuid_short' => substr((string)($d['device_uuid'] ?? ''), 0, 8),
            'is_online' => $is_online,
            'minutes_ago' => $minutes_ago,
            'has_issues' => (int)($d['has_issues'] ?? 0) === 1,
            'alarms_critical' => (int)($d['alarms_critical'] ?? 0),
            'alarms_total' => (int)($d['alarms_total'] ?? 0),
            'controllers_offline' => (int)($d['controllers_offline'] ?? 0),
            'software_version' => $d['software_version'],
        ];
    }

    // AI suggestion governance counts (tolerate missing tables)
    $suggestion_counts = [
        'pending' => 0, 'delivered' => 0, 'read' => 0,
        'acted_upon' => 0, 'dismissed' => 0, 'retracted' => 0,
    ];
    $flagged_responses = 0;
    $recent_suggestions = [];

    try {
        $rows = $pdo->query("
            SELECT status, COUNT(*) AS c FROM ai_suggestions GROUP BY status
        ")->fetchAll(PDO::FETCH_KEY_PAIR);
        foreach ($rows as $status => $count) {
            $suggestion_counts[$status] = (int)$count;
        }

        $flagged_responses = (int)$pdo->query("
            SELECT COUNT(*) FROM ai_responses WHERE flagged = 1
        ")->fetchColumn();

        $recent_suggestions = $pdo->query("
            SELECT s.id, s.title, s.status, s.priority, s.suggestion_type,
                   s.created_at, COALESCE(d.alias, d.name) AS device_name
            FROM ai_suggestions s
            JOIN pi_devices d ON s.device_id = d.id
            WHERE s.status IN ('pending','delivered','read')
            ORDER BY s.created_at DESC
            LIMIT 5
        ")->fetchAll(PDO::FETCH_ASSOC);
    } catch (PDOException $e) {
        // AI tables not provisioned yet - leave zeros
    }

    // Latest staff check-in
    $last_checkin = null;
    try {
        $last_checkin = $pdo->query("
            SELECT id, admin_username, status, note, created_at
            FROM staff_checkins
            ORDER BY created_at DESC
            LIMIT 1
        ")->fetch(PDO::FETCH_ASSOC) ?: null;
    } catch (PDOException $e) {
        // Migration not run yet - caller will see null and prompt to migrate
    }

    successResponse([
        'staff' => [
            'username' => $_SESSION['admin_username'] ?? 'staff',
        ],
        'fleet' => [
            'total' => count($device_list),
            'online' => $online,
            'offline' => $offline,
            'with_issues' => $with_issues,
            'alarms_critical' => $critical,
        ],
        'ai' => [
            'suggestions' => $suggestion_counts,
            'flagged_responses' => $flagged_responses,
            'review_queue' => (int)$suggestion_counts['pending']
                           + (int)$suggestion_counts['delivered']
                           + (int)$suggestion_counts['read']
                           + (int)$flagged_responses,
        ],
        'recent_suggestions' => $recent_suggestions,
        'last_checkin' => $last_checkin,
        'devices' => $device_list,
    ]);
} catch (PDOException $e) {
    errorResponse('Database error', 500);
}
