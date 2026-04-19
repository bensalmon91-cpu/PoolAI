<?php
/**
 * PoolAIssistant Cloud Upload Endpoint
 *
 * Receives periodic snapshot uploads from Pi devices containing:
 * - Pool chemistry readings (pH, chlorine, ORP, temperature)
 * - Device health metrics (CPU, memory, disk, uptime)
 * - Controller status (online/offline)
 * - Active alarms
 *
 * POST /api/device/snapshot.php
 * Headers: Authorization: Bearer <api_key>
 * Body: JSON snapshot payload
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';

header('Content-Type: application/json');

// Only accept POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

// Authenticate device
$device = authenticateDevice();
if (!$device) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Invalid or missing API key']);
    exit;
}

$deviceId = $device['id'];

// Parse JSON body
$input = file_get_contents('php://input');
$payload = json_decode($input, true);

if (!$payload || !is_array($payload)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Invalid JSON payload']);
    exit;
}

$pdo = db();

try {
    $pdo->beginTransaction();

    $timestamp = $payload['timestamp'] ?? date('Y-m-d H:i:s');
    $readings = $payload['readings'] ?? [];
    $health = $payload['health'] ?? [];
    $controllers = $payload['controllers'] ?? [];
    $alarms = $payload['alarms'] ?? [];

    // =========================================================================
    // STORE READINGS
    // =========================================================================

    if (!empty($readings) && is_array($readings)) {
        // Prepare statements for latest and history tables
        $stmtLatest = $pdo->prepare("
            INSERT INTO device_readings_latest
                (device_id, pool, metric, value, unit, ts, received_at)
            VALUES (?, ?, ?, ?, ?, ?, NOW())
            ON DUPLICATE KEY UPDATE
                value = VALUES(value),
                unit = VALUES(unit),
                ts = VALUES(ts),
                received_at = NOW()
        ");

        $stmtHistory = $pdo->prepare("
            INSERT INTO device_readings_history
                (device_id, pool, metric, value, unit, ts, received_at)
            VALUES (?, ?, ?, ?, ?, ?, NOW())
        ");

        foreach ($readings as $reading) {
            $pool = $reading['pool'] ?? '';
            $metric = $reading['metric'] ?? '';
            $value = $reading['value'] ?? null;
            $unit = $reading['unit'] ?? null;
            $ts = $reading['ts'] ?? $timestamp;

            if (!$metric || $value === null) {
                continue;
            }

            // Detect unit from metric if not provided
            if (!$unit) {
                $unit = detectUnit($metric);
            }

            // Update latest reading
            $stmtLatest->execute([$deviceId, $pool, $metric, $value, $unit, $ts]);

            // Store in history
            $stmtHistory->execute([$deviceId, $pool, $metric, $value, $unit, $ts]);
        }
    }

    // =========================================================================
    // STORE CONTROLLER STATUS
    // =========================================================================

    if (!empty($controllers) && is_array($controllers)) {
        $stmtCtrl = $pdo->prepare("
            INSERT INTO device_controllers_status
                (device_id, host, name, is_online, minutes_ago, received_at)
            VALUES (?, ?, ?, ?, ?, NOW())
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                is_online = VALUES(is_online),
                minutes_ago = VALUES(minutes_ago),
                received_at = NOW()
        ");

        foreach ($controllers as $ctrl) {
            $host = $ctrl['host'] ?? '';
            $name = $ctrl['name'] ?? $host;
            $online = !empty($ctrl['online']) ? 1 : 0;
            $minutesAgo = $ctrl['minutes_ago'] ?? null;

            if (!$host) continue;

            $stmtCtrl->execute([$deviceId, $host, $name, $online, $minutesAgo]);
        }
    }

    // =========================================================================
    // STORE ALARMS
    // =========================================================================

    // Each snapshot is authoritative: wipe prior "current" rows and re-insert
    // whatever the Pi reports, including the empty case (all alarms cleared).
    $pdo->prepare("DELETE FROM device_alarms_current WHERE device_id = ?")->execute([$deviceId]);

    if (!empty($alarms['active']) && is_array($alarms['active'])) {
        $stmtAlarm = $pdo->prepare("
            INSERT INTO device_alarms_current
                (device_id, pool, alarm_source, alarm_name, severity, started_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, NOW())
        ");

        foreach ($alarms['active'] as $alarm) {
            $pool = $alarm['pool'] ?? '';
            $source = $alarm['source'] ?? 'Unknown';
            $since = $alarm['since'] ?? date('Y-m-d H:i:s');

            // Determine severity
            $severity = 'warning';
            if (stripos($source, 'critical') !== false ||
                stripos($source, 'emergency') !== false ||
                stripos($source, 'fail') !== false) {
                $severity = 'critical';
            }

            $stmtAlarm->execute([$deviceId, $pool, $source, $source, $severity, $since]);
        }
    }

    // =========================================================================
    // UPDATE DEVICE HEALTH
    // =========================================================================

    $controllersOnline = $health['controllers_online'] ?? 0;
    $controllersOffline = $health['controllers_offline'] ?? 0;
    $alarmsTotal = $alarms['total'] ?? 0;
    $alarmsCritical = $alarms['critical'] ?? 0;
    $alarmsWarning = $alarms['warning'] ?? 0;

    // Check for issues
    $issues = [];
    $hasIssues = false;

    if ($alarmsCritical > 0) {
        $issues[] = "$alarmsCritical critical alarm(s)";
        $hasIssues = true;
    }
    if ($controllersOffline > 0) {
        $issues[] = "$controllersOffline controller(s) offline";
        $hasIssues = true;
    }
    if (($health['disk_used_pct'] ?? 0) > 90) {
        $issues[] = "Disk usage above 90%";
        $hasIssues = true;
    }
    if (($health['cpu_temp'] ?? 0) > 75) {
        $issues[] = "CPU temperature high";
        $hasIssues = true;
    }

    $stmtHealth = $pdo->prepare("
        INSERT INTO device_health
            (device_id, ts, uptime_seconds, disk_used_pct, memory_used_pct, cpu_temp,
             controllers_online, controllers_offline, controllers_json,
             alarms_total, alarms_critical, alarms_warning,
             has_issues, issues_json)
        VALUES (?, NOW(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");

    $stmtHealth->execute([
        $deviceId,
        $health['uptime_seconds'] ?? null,
        $health['disk_used_pct'] ?? null,
        $health['memory_used_pct'] ?? null,
        $health['cpu_temp'] ?? null,
        $controllersOnline,
        $controllersOffline,
        json_encode($controllers),
        $alarmsTotal,
        $alarmsCritical,
        $alarmsWarning,
        $hasIssues ? 1 : 0,
        json_encode($issues),
    ]);

    // Update device last_seen
    $pdo->prepare("UPDATE pi_devices SET last_seen = NOW() WHERE id = ?")->execute([$deviceId]);

    // =========================================================================
    // LOG SNAPSHOT
    // =========================================================================

    $payloadSize = strlen($input);
    $stmtLog = $pdo->prepare("
        INSERT INTO device_snapshot_log
            (device_id, readings_count, alarms_count, controllers_count, payload_size, ip_address, received_at)
        VALUES (?, ?, ?, ?, ?, ?, NOW())
    ");
    $stmtLog->execute([
        $deviceId,
        count($readings),
        $alarmsTotal,
        count($controllers),
        $payloadSize,
        $_SERVER['REMOTE_ADDR'] ?? null,
    ]);

    $pdo->commit();

    // Calculate next upload time (in 6 minutes)
    $nextUploadAt = date('Y-m-d\TH:i:s\Z', strtotime('+6 minutes'));

    echo json_encode([
        'ok' => true,
        'message' => 'Snapshot received',
        'readings_stored' => count($readings),
        'next_upload_at' => $nextUploadAt,
    ]);

} catch (PDOException $e) {
    $pdo->rollBack();
    error_log("Snapshot error for device $deviceId: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Database error']);
} catch (Exception $e) {
    $pdo->rollBack();
    error_log("Snapshot error for device $deviceId: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Server error']);
}

/**
 * Detect unit from metric name
 */
function detectUnit(string $metric): ?string {
    $metric = strtolower($metric);

    if (strpos($metric, 'temp') !== false) {
        return '°C';
    }
    if (strpos($metric, 'ph') !== false) {
        return '';  // pH is unitless
    }
    if (strpos($metric, 'chlorine') !== false || strpos($metric, 'cl') !== false) {
        return 'mg/L';
    }
    if (strpos($metric, 'orp') !== false) {
        return 'mV';
    }
    if (strpos($metric, 'tds') !== false) {
        return 'ppm';
    }
    if (strpos($metric, 'conductivity') !== false) {
        return 'µS/cm';
    }
    if (strpos($metric, 'turbidity') !== false) {
        return 'NTU';
    }
    if (strpos($metric, 'flow') !== false) {
        return 'L/min';
    }
    if (strpos($metric, 'pressure') !== false) {
        return 'bar';
    }

    return null;
}
