<?php
/**
 * Mobile API: Device Detail / Update / Delete
 *
 * GET    /api/mobile/device.php?id=X     - Get device details
 * PATCH  /api/mobile/device.php?id=X     - Update device (nickname)
 * DELETE /api/mobile/device.php?id=X     - Unlink device
 *
 * Headers: Authorization: Bearer <access_token>
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, PATCH, DELETE, OPTIONS');
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

$deviceId = isset($_GET['id']) ? (int)$_GET['id'] : 0;

if (!$deviceId) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Device ID required']);
    exit;
}

$devices = new MobileDevices($user['id']);

switch ($_SERVER['REQUEST_METHOD']) {
    case 'GET':
        $device = $devices->getDevice($deviceId);

        if (!$device) {
            http_response_code(404);
            echo json_encode(['ok' => false, 'error' => 'Device not found']);
            exit;
        }

        echo json_encode([
            'ok' => true,
            'device' => $device
        ]);
        break;

    case 'PATCH':
        $input = json_decode(file_get_contents('php://input'), true);

        if (isset($input['nickname'])) {
            $result = $devices->updateNickname($deviceId, $input['nickname']);
            http_response_code($result['ok'] ? 200 : 400);
            echo json_encode($result);
        } else {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'No valid fields to update']);
        }
        break;

    case 'DELETE':
        $result = $devices->unlinkDevice($deviceId);
        http_response_code($result['ok'] ? 200 : 400);
        echo json_encode($result);
        break;

    default:
        http_response_code(405);
        echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
}
