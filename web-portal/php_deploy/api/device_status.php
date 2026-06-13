<?php
/**
 * Device Status API
 * Receives test results from Pi devices and updates their status
 *
 * POST /api/device_status.php
 * Headers: X-API-Key: <device-api-key>
 * Body: { "device_id": "...", "tests": {...}, "overall": "PASS|FAIL", "timestamp": "..." }
 *
 * GET /api/device_status.php
 * Headers: X-API-Key: <device-api-key>
 * Returns current device status
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

// Authenticate device
$api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (empty($api_key)) {
    errorResponse('Missing API key', 401);
}

$pdo = db();

// Verify API key and get device
$stmt = $pdo->prepare("SELECT id, name, device_uuid, last_seen FROM pi_devices WHERE api_key = ? AND is_active = 1");
$stmt->execute([$api_key]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$device) {
    errorResponse('Invalid API key', 401);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // Receive status update from Pi
    $input = json_decode(file_get_contents('php://input'), true);

    if (!$input) {
        errorResponse('Invalid JSON body', 400);
    }

    $test_results = json_encode($input['tests'] ?? []);
    $overall_status = $input['overall'] ?? 'UNKNOWN';
    $device_alias = $input['device_alias'] ?? '';
    $timestamp = $input['timestamp'] ?? date('c');

    // Update device record
    $stmt = $pdo->prepare("
        UPDATE pi_devices SET
            last_seen = NOW(),
            last_test_status = ?,
            last_test_results = ?,
            last_test_at = NOW(),
            name = COALESCE(NULLIF(?, ''), name)
        WHERE id = ?
    ");
    $stmt->execute([$overall_status, $test_results, $device_alias, $device['id']]);

    // Log the status report
    $log_stmt = $pdo->prepare("
        INSERT INTO device_activity_log (device_id, action, ip_address, details)
        VALUES (?, 'status_report', ?, ?)
    ");
    $log_stmt->execute([
        $device['id'],
        $_SERVER['REMOTE_ADDR'] ?? null,
        json_encode([
            'overall' => $overall_status,
            'tests' => $input['tests'] ?? []
        ])
    ]);

    jsonResponse([
        'ok' => true,
        'message' => 'Status updated',
        'device_name' => $device['name']
    ]);

} elseif ($_SERVER['REQUEST_METHOD'] === 'GET') {
    // Return current device status
    jsonResponse([
        'ok' => true,
        'device_id' => $device['id'],
        'device_name' => $device['name'],
        'device_uuid' => $device['device_uuid'],
        'last_seen' => $device['last_seen']
    ]);

} else {
    errorResponse('Method not allowed', 405);
}
