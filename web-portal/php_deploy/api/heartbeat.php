<?php
/**
 * Device Heartbeat API Endpoint
 * Receives health status from Pi devices and returns pending commands
 *
 * POST /api/heartbeat.php
 * Headers: X-API-Key: <device-api-key> OR Authorization: Bearer <api-key>
 * Body: JSON with health data
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/ai/heartbeat_extension.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

// Get API key from header (support both X-API-Key and Authorization: Bearer)
$api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (empty($api_key)) {
    $auth_header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (stripos($auth_header, 'Bearer ') === 0) {
        $api_key = substr($auth_header, 7);
    }
}

if (empty($api_key)) {
    errorResponse('Missing API key', 401);
}

$pdo = db();

// Verify API key and get device
$stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE api_key = ? AND is_active = 1");
$stmt->execute([$api_key]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$device) {
    errorResponse('Invalid API key', 401);
}

$device_id = $device['id'];

// Get JSON body
$input = getJsonInput();

// Insert health record
try {
    $stmt = $pdo->prepare("
        INSERT INTO device_health
        (device_id, uptime_seconds, disk_used_pct, memory_used_pct, cpu_temp,
         last_upload_success, last_upload_error, pending_chunks, failed_uploads,
         software_version, ip_address,
         controllers_online, controllers_offline, controllers_json,
         alarms_total, alarms_critical, alarms_warning,
         issues_json, has_issues)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");

    $last_upload_success = !empty($input['last_upload_success'])
        ? date('Y-m-d H:i:s', strtotime($input['last_upload_success']))
        : null;

    // Encode arrays as JSON for storage
    $controllers_json = !empty($input['controllers']) ? json_encode($input['controllers']) : null;
    $issues_json = !empty($input['issues']) ? json_encode($input['issues']) : null;

    $stmt->execute([
        $device_id,
        $input['uptime_seconds'] ?? null,
        $input['disk_used_pct'] ?? null,
        $input['memory_used_pct'] ?? null,
        $input['cpu_temp'] ?? null,
        $last_upload_success,
        $input['last_upload_error'] ?? null,
        $input['pending_chunks'] ?? 0,
        $input['failed_uploads'] ?? 0,
        $input['software_version'] ?? null,
        $input['ip_address'] ?? ($_SERVER['REMOTE_ADDR'] ?? null),
        // New v2 fields
        $input['controllers_online'] ?? 0,
        $input['controllers_offline'] ?? 0,
        $controllers_json,
        $input['alarms_total'] ?? 0,
        $input['alarms_critical'] ?? 0,
        $input['alarms_warning'] ?? 0,
        $issues_json,
        !empty($input['has_issues']) ? 1 : 0,
    ]);

    // Update device last_seen
    $stmt = $pdo->prepare("UPDATE pi_devices SET last_seen = NOW() WHERE id = ?");
    $stmt->execute([$device_id]);

    // Check for pending commands
    $stmt = $pdo->prepare("
        SELECT id, command_type, payload
        FROM device_commands
        WHERE device_id = ? AND status = 'pending'
        ORDER BY created_at ASC
    ");
    $stmt->execute([$device_id]);
    $commands = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Mark commands as acknowledged
    if (!empty($commands)) {
        $ids = array_column($commands, 'id');
        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $stmt = $pdo->prepare("
            UPDATE device_commands
            SET status = 'acknowledged', acknowledged_at = NOW()
            WHERE id IN ($placeholders)
        ");
        $stmt->execute($ids);
    }

    // Check for alert conditions and send email if needed
    checkAndSendAlerts($pdo, $device_id, $device['name'], $input);

    // AI Assistant Integration - process incoming responses/actions
    if (!empty($input['ai'])) {
        processAIHeartbeatInput($pdo, $device_id, $input['ai']);
    }

    // Get AI data for response (questions and suggestions)
    $ai_data = getAIHeartbeatData($pdo, $device_id);

    // Alias sync disabled - columns don't exist in database yet
    // To enable: run fix_devices.php to add alias columns, then restore this code
    $sync_alias = null;

    jsonResponse([
        'ok' => true,
        'commands' => $commands,
        'alias_sync' => $sync_alias,
        'ai' => $ai_data
    ]);

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}

/**
 * Check for alert conditions and send email
 */
function checkAndSendAlerts($pdo, $device_id, $device_name, $health_data) {
    $alert_email = defined('ALERT_EMAIL') ? ALERT_EMAIL : '';
    if (empty($alert_email)) {
        return;
    }

    $failed_uploads = intval($health_data['failed_uploads'] ?? 0);
    $controllers_offline = intval($health_data['controllers_offline'] ?? 0);
    $alarms_critical = intval($health_data['alarms_critical'] ?? 0);
    $has_issues = !empty($health_data['has_issues']);
    $issues = $health_data['issues'] ?? [];

    // Alert on upload failures (more than 3)
    if ($failed_uploads > 3) {
        sendAlertIfNotRecent($pdo, $device_id, 'upload_failure', 2,
            "[PoolDash Alert] Upload Failures: $device_name",
            "Device is experiencing upload failures.\n\n"
            . "Device: $device_name\n"
            . "Failed uploads: $failed_uploads\n"
            . "Last error: " . ($health_data['last_upload_error'] ?? 'Unknown') . "\n\n"
            . "The device will automatically retry uploads.\n\n"
            . "--\nPoolDash Monitoring"
        );
    }

    // Alert on controllers offline
    if ($controllers_offline > 0) {
        $controllers = $health_data['controllers'] ?? [];
        $offline_hosts = [];
        foreach ($controllers as $c) {
            if (empty($c['online'])) {
                $offline_hosts[] = $c['host'] ?? 'unknown';
            }
        }
        $host_list = implode(', ', $offline_hosts);

        sendAlertIfNotRecent($pdo, $device_id, 'controller_offline', 4,
            "[PoolDash Alert] Controllers Offline: $device_name",
            "One or more pool controllers are not communicating.\n\n"
            . "Device: $device_name\n"
            . "Controllers offline: $controllers_offline\n"
            . "Hosts: $host_list\n\n"
            . "Check network connectivity and controller power.\n\n"
            . "--\nPoolDash Monitoring"
        );
    }

    // Alert on critical alarms
    if ($alarms_critical > 0) {
        sendAlertIfNotRecent($pdo, $device_id, 'critical_alarm', 6,
            "[PoolDash Alert] Critical Alarms: $device_name",
            "There are critical alarms active on the pool system.\n\n"
            . "Device: $device_name\n"
            . "Critical alarms: $alarms_critical\n"
            . "Total alarms: " . ($health_data['alarms_total'] ?? 0) . "\n\n"
            . "Please check the PoolDash dashboard for details.\n\n"
            . "--\nPoolDash Monitoring"
        );
    }

    // Alert on any issues (summary)
    if ($has_issues && !empty($issues)) {
        $issues_text = is_array($issues) ? implode("\n  - ", $issues) : $issues;
        sendAlertIfNotRecent($pdo, $device_id, 'has_issues', 2,
            "[PoolDash Alert] Issues Detected: $device_name",
            "The device has detected issues that need attention.\n\n"
            . "Device: $device_name\n"
            . "Issues:\n  - $issues_text\n\n"
            . "Please check the PoolDash dashboard for details.\n\n"
            . "--\nPoolDash Monitoring"
        );
    }
}

/**
 * Send alert if not sent recently
 */
function sendAlertIfNotRecent($pdo, $device_id, $alert_type, $hours, $subject, $body) {
    $stmt = $pdo->prepare("
        SELECT COUNT(*) FROM alert_log
        WHERE device_id = ? AND alert_type = ?
        AND sent_at > DATE_SUB(NOW(), INTERVAL ? HOUR)
    ");
    $stmt->execute([$device_id, $alert_type, $hours]);

    if ($stmt->fetchColumn() == 0) {
        if (sendAlertEmail($subject, $body)) {
            $stmt = $pdo->prepare("
                INSERT INTO alert_log (device_id, alert_type) VALUES (?, ?)
            ");
            $stmt->execute([$device_id, $alert_type]);
        }
    }
}

/**
 * Send alert email
 */
function sendAlertEmail($subject, $body) {
    $to = defined('ALERT_EMAIL') ? ALERT_EMAIL : '';
    if (empty($to)) {
        return false;
    }

    $from = defined('SMTP_FROM') ? SMTP_FROM : 'alerts@poolaissistant.modprojects.co.uk';
    $headers = "From: $from\r\n"
             . "Reply-To: $from\r\n"
             . "X-Mailer: PHP/" . phpversion();

    return mail($to, $subject, $body, $headers);
}
