<?php
/**
 * Mobile API: Device List
 *
 * GET /api/mobile/devices
 * Headers: Authorization: Bearer <access_token>
 * Response: { ok, devices: [...] }
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

$devices = new MobileDevices($user['id']);
$deviceList = $devices->getDevices();

echo json_encode([
    'ok' => true,
    'devices' => $deviceList
]);
