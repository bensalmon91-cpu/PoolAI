<?php
/**
 * Mobile API: Device Health Data
 *
 * GET /api/mobile/health.php?device_id=X            - Get current health
 * GET /api/mobile/health.php?device_id=X&hours=24   - Get health history
 *
 * Headers: Authorization: Bearer <access_token>
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

require_once __DIR__ . '/../../includes/MobileAuth.php';
require_once __DIR__ . '/../../includes/MobileDevices.php';

$auth = new MobileAuth();
$user = $auth->requireAuth();

$deviceId = isset($_GET['device_id']) ? (int)$_GET['device_id'] : 0;

if (!$deviceId) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Device ID required']);
    exit;
}

$devices = new MobileDevices($user['id']);

if (!$devices->hasAccess($deviceId)) {
    http_response_code(404);
    echo json_encode(['ok' => false, 'error' => 'Device not found']);
    exit;
}

// Check if history requested
if (isset($_GET['hours'])) {
    $hours = min(168, max(1, (int)$_GET['hours'])); // 1 hour to 1 week
    $history = $devices->getHealthHistory($deviceId, $hours);

    echo json_encode([
        'ok' => true,
        'history' => $history
    ]);
} else {
    // Current health
    $health = $devices->getDeviceHealth($deviceId);

    if (!$health) {
        http_response_code(404);
        echo json_encode(['ok' => false, 'error' => 'No health data available']);
        exit;
    }

    echo json_encode([
        'ok' => true,
        'health' => $health
    ]);
}
