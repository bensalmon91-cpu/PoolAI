<?php
/**
 * AI Response Submission API - Device endpoint for submitting answers
 *
 * POST /api/ai/response.php
 * Headers: X-API-Key: <device-api-key>
 * Body: { queue_id, answer, answer_json?, answered_at }
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

// Get API key from header
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
$stmt = $pdo->prepare("SELECT id FROM pi_devices WHERE api_key = ? AND is_active = 1");
$stmt->execute([$api_key]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$device) {
    errorResponse('Invalid API key', 401);
}

$device_id = $device['id'];

$input = getJsonInput();

// Validate required fields
$required = ['queue_id', 'answer'];
if ($error = validateRequired($required, $input)) {
    errorResponse($error);
}

try {
    // Get queue entry and verify it belongs to this device
    $stmt = $pdo->prepare("
        SELECT qq.*, q.text as question_text, q.type as question_type
        FROM ai_question_queue qq
        JOIN ai_questions q ON qq.question_id = q.id
        WHERE qq.id = ? AND qq.device_id = ?
    ");
    $stmt->execute([$input['queue_id'], $device_id]);
    $queue = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$queue) {
        errorResponse('Queue entry not found or does not belong to this device', 404);
    }

    if ($queue['status'] === 'answered') {
        errorResponse('Question already answered');
    }

    $answered_at = $input['answered_at'] ?? date('Y-m-d H:i:s');

    // Insert response
    $stmt = $pdo->prepare("
        INSERT INTO ai_responses
        (device_id, question_id, queue_id, pool, answer, answer_json, answered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $device_id,
        $queue['question_id'],
        $queue['id'],
        $queue['pool'],
        $input['answer'],
        isset($input['answer_json']) ? json_encode($input['answer_json']) : null,
        $answered_at
    ]);

    // Update queue status
    $stmt = $pdo->prepare("
        UPDATE ai_question_queue
        SET status = 'answered', answered_at = ?
        WHERE id = ?
    ");
    $stmt->execute([$answered_at, $queue['id']]);

    // Update pool profile question count and timestamp
    $stmt = $pdo->prepare("
        INSERT INTO ai_pool_profiles (device_id, pool, profile_json, questions_answered, last_question_at)
        VALUES (?, ?, '{}', 1, ?)
        ON DUPLICATE KEY UPDATE
            questions_answered = questions_answered + 1,
            last_question_at = VALUES(last_question_at)
    ");
    $stmt->execute([$device_id, $queue['pool'], $answered_at]);

    // Check if there's a next pending question to return
    $stmt = $pdo->prepare("
        SELECT qq.id as queue_id, qq.pool,
               q.id as question_id, q.text, q.input_type, q.options_json, q.priority
        FROM ai_question_queue qq
        JOIN ai_questions q ON qq.question_id = q.id
        WHERE qq.device_id = ? AND qq.status = 'pending'
              AND (qq.expires_at IS NULL OR qq.expires_at > NOW())
        ORDER BY q.priority DESC, qq.created_at ASC
        LIMIT 1
    ");
    $stmt->execute([$device_id]);
    $next_question = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($next_question && $next_question['options_json']) {
        $next_question['options'] = json_decode($next_question['options_json'], true);
        unset($next_question['options_json']);
    }

    successResponse([
        'next_question' => $next_question ?: null
    ], 'Response recorded');

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
