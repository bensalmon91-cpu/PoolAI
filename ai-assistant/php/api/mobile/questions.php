<?php
/**
 * Mobile API: AI Questions
 *
 * GET  /api/mobile/questions.php?device_id=X         - Get pending questions
 * POST /api/mobile/questions.php?device_id=X&id=Y    - Submit answer
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
        $questions = $devices->getPendingQuestions($deviceId);

        echo json_encode([
            'ok' => true,
            'questions' => $questions
        ]);
        break;

    case 'POST':
        $queueId = isset($_GET['id']) ? (int)$_GET['id'] : 0;

        if (!$queueId) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Queue ID required']);
            exit;
        }

        $input = json_decode(file_get_contents('php://input'), true);
        $answer = trim($input['answer'] ?? '');
        $answerJson = $input['answer_json'] ?? null;

        if (empty($answer)) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Answer is required']);
            exit;
        }

        $result = $devices->answerQuestion($deviceId, $queueId, $answer, $answerJson);
        http_response_code($result['ok'] ? 200 : 400);
        echo json_encode($result);
        break;

    default:
        http_response_code(405);
        echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
}
