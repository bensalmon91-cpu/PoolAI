<?php
/**
 * Mobile API: Notification Preferences
 *
 * GET   /api/mobile/notifications.php                - Get preferences
 * PATCH /api/mobile/notifications.php                - Update global preferences
 * PATCH /api/mobile/notifications.php?device_id=X   - Update device-specific preferences
 *
 * Headers: Authorization: Bearer <access_token>
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, PATCH, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

require_once __DIR__ . '/../../includes/MobileAuth.php';
require_once __DIR__ . '/../../includes/MobileDevices.php';

$auth = new MobileAuth();
$user = $auth->requireAuth();

$devices = new MobileDevices($user['id']);
$deviceId = isset($_GET['device_id']) ? (int)$_GET['device_id'] : null;

// If device-specific, verify access
if ($deviceId && !$devices->hasAccess($deviceId)) {
    http_response_code(404);
    echo json_encode(['ok' => false, 'error' => 'Device not found']);
    exit;
}

switch ($_SERVER['REQUEST_METHOD']) {
    case 'GET':
        $prefs = $devices->getNotificationPrefs($deviceId);
        echo json_encode([
            'ok' => true,
            'preferences' => $prefs
        ]);
        break;

    case 'PATCH':
        $input = json_decode(file_get_contents('php://input'), true);

        if (!$input) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Invalid JSON body']);
            exit;
        }

        $result = $devices->updateNotificationPrefs($input, $deviceId);
        http_response_code($result['ok'] ? 200 : 400);
        echo json_encode($result);
        break;

    default:
        http_response_code(405);
        echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
}
