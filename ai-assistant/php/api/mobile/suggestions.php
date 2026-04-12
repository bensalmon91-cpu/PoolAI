<?php
/**
 * Mobile API: AI Suggestions
 *
 * GET  /api/mobile/suggestions.php?device_id=X           - Get suggestions
 * POST /api/mobile/suggestions.php?device_id=X&id=Y      - Submit feedback
 *
 * Headers: Authorization: Bearer <access_token>
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
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

switch ($_SERVER['REQUEST_METHOD']) {
    case 'GET':
        $limit = isset($_GET['limit']) ? min(50, max(1, (int)$_GET['limit'])) : 10;
        $status = isset($_GET['status']) ? $_GET['status'] : null;

        $suggestions = $devices->getAISuggestions($deviceId, $limit, $status);

        echo json_encode([
            'ok' => true,
            'suggestions' => $suggestions
        ]);
        break;

    case 'POST':
        $suggestionId = isset($_GET['id']) ? (int)$_GET['id'] : 0;

        if (!$suggestionId) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Suggestion ID required']);
            exit;
        }

        $input = json_decode(file_get_contents('php://input'), true);
        $action = $input['action'] ?? '';
        $feedback = $input['feedback'] ?? null;

        if (!in_array($action, ['read', 'acted_upon', 'dismissed'])) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Invalid action. Must be read, acted_upon, or dismissed']);
            exit;
        }

        $result = $devices->suggestionFeedback($deviceId, $suggestionId, $action, $feedback);
        http_response_code($result['ok'] ? 200 : 400);
        echo json_encode($result);
        break;

    default:
        http_response_code(405);
        echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
}
