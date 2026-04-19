<?php
/**
 * Queue Test Question API
 * Queues a test question to a specific device
 * Requires admin session authentication
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

header('Content-Type: application/json');

// Require admin login (uses startSecureSession with correct session name)
if (!isAdmin()) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

$input = json_decode(file_get_contents('php://input'), true);
$device_id = isset($input['device_id']) ? (int)$input['device_id'] : 0;

if (!$device_id) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'device_id required']);
    exit;
}

try {
    $pdo = db();

    // Verify device exists
    $stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE id = ? AND is_active = 1");
    $stmt->execute([$device_id]);
    $device = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$device) {
        http_response_code(404);
        echo json_encode(['ok' => false, 'error' => 'Device not found']);
        exit;
    }

    // Get first active question
    $question = $pdo->query("SELECT id, text FROM ai_questions WHERE is_active = 1 ORDER BY id LIMIT 1")->fetch(PDO::FETCH_ASSOC);
    if (!$question) {
        echo json_encode(['ok' => false, 'error' => 'No questions found in database. Add questions first.']);
        exit;
    }

    // Check for existing pending question
    $stmt = $pdo->prepare("SELECT id FROM ai_question_queue WHERE device_id = ? AND question_id = ? AND status = 'pending'");
    $stmt->execute([$device_id, $question['id']]);
    if ($stmt->fetch()) {
        echo json_encode(['ok' => false, 'error' => 'Question already queued for this device']);
        exit;
    }

    // Queue the question
    $stmt = $pdo->prepare("
        INSERT INTO ai_question_queue (device_id, question_id, pool, triggered_by, status, expires_at)
        VALUES (?, ?, '', 'admin_test', 'pending', DATE_ADD(NOW(), INTERVAL 24 HOUR))
    ");
    $stmt->execute([$device_id, $question['id']]);
    $queue_id = $pdo->lastInsertId();

    echo json_encode([
        'ok' => true,
        'queue_id' => $queue_id,
        'device_name' => $device['name'],
        'question' => $question['text']
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Database error: ' . $e->getMessage()]);
}
