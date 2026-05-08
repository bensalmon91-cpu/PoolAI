<?php
/**
 * Admin Device Health API Endpoint
 * Returns health status for all devices
 *
 * GET /api/admin_health.php
 * Requires admin session
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/../includes/auth.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    errorResponse('Method not allowed', 405);
}

// Require admin authentication
if (!isAdmin()) {
    errorResponse('Admin authentication required', 401);
}

$pdo = db();

try {
    // Get latest health record for each device
    $stmt = $pdo->query("
        SELECT
            h.device_id,
            h.ts as health_ts,
            h.uptime_seconds,
            h.disk_used_pct,
            h.memory_used_pct,
            h.cpu_temp,
            h.last_upload_success,
            h.last_upload_error,
            h.pending_chunks,
            h.failed_uploads,
            h.software_version,
            h.ip_address,
            h.controllers_online,
            h.controllers_offline,
            h.controllers_json,
            h.alarms_total,
            h.alarms_critical,
            h.alarms_warning,
            h.issues_json,
            h.has_issues,
            d.name as device_name,
            d.last_seen
        FROM device_health h
        INNER JOIN (
            SELECT device_id, MAX(ts) as max_ts
            FROM device_health
            GROUP BY device_id
        ) latest ON h.device_id = latest.device_id AND h.ts = latest.max_ts
        JOIN pi_devices d ON h.device_id = d.id
        WHERE d.is_active = 1
        ORDER BY d.name
    ");

    $devices = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Calculate online status (seen in last 20 minutes) and decode JSON fields
    $now = time();
    foreach ($devices as &$device) {
        $last_seen = $device['last_seen'] ? strtotime($device['last_seen']) : null;
        $minutes_ago = $last_seen ? round(($now - $last_seen) / 60) : null;
        $device['is_online'] = $minutes_ago !== null && $minutes_ago < 20;
        $device['minutes_since_seen'] = $minutes_ago;

        // Decode JSON fields
        $device['controllers'] = !empty($device['controllers_json'])
            ? json_decode($device['controllers_json'], true) : [];
        $device['issues'] = !empty($device['issues_json'])
            ? json_decode($device['issues_json'], true) : [];

        // Clean up raw JSON columns
        unset($device['controllers_json']);
        unset($device['issues_json']);
    }

    jsonResponse($devices);

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
