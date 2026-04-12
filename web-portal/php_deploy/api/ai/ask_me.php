<?php
/**
 * AI Ask Me API - User-initiated question request
 *
 * POST /api/ai/ask_me.php
 * Headers: X-API-Key: <device-api-key>
 * Body: { pool }
 *
 * Returns the next most relevant question for this device/pool,
 * considering profile maturity, unanswered questions, and recent events.
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
$pool = $input['pool'] ?? '';

try {
    // Get pool profile to determine maturity
    $stmt = $pdo->prepare("
        SELECT maturity_score, questions_answered, last_question_at
        FROM ai_pool_profiles
        WHERE device_id = ? AND pool = ?
    ");
    $stmt->execute([$device_id, $pool]);
    $profile = $stmt->fetch(PDO::FETCH_ASSOC);

    $maturity = $profile['maturity_score'] ?? 0;
    $questions_answered = $profile['questions_answered'] ?? 0;

    // Get questions this device has already answered
    $stmt = $pdo->prepare("
        SELECT question_id FROM ai_responses
        WHERE device_id = ? AND pool = ?
    ");
    $stmt->execute([$device_id, $pool]);
    $answered_ids = $stmt->fetchAll(PDO::FETCH_COLUMN);

    // Get questions currently pending in queue
    $stmt = $pdo->prepare("
        SELECT question_id FROM ai_question_queue
        WHERE device_id = ? AND pool = ? AND status = 'pending'
    ");
    $stmt->execute([$device_id, $pool]);
    $pending_ids = $stmt->fetchAll(PDO::FETCH_COLUMN);

    $exclude_ids = array_merge($answered_ids, $pending_ids);

    // Build query to find next best question
    // Priority: onboarding (if new) > event > periodic > contextual
    $exclude_clause = '';
    $params = [];

    if (!empty($exclude_ids)) {
        $placeholders = implode(',', array_fill(0, count($exclude_ids), '?'));
        $exclude_clause = "AND q.id NOT IN ($placeholders)";
        $params = $exclude_ids;
    }

    // Determine question type priority based on maturity
    if ($maturity < 25) {
        // New pool - prioritize onboarding
        $type_order = "FIELD(q.type, 'onboarding', 'event', 'periodic', 'contextual', 'followup')";
    } elseif ($maturity < 50) {
        // Developing - mix of onboarding and periodic
        $type_order = "FIELD(q.type, 'event', 'onboarding', 'periodic', 'contextual', 'followup')";
    } else {
        // Established - focus on event/periodic
        $type_order = "FIELD(q.type, 'event', 'periodic', 'contextual', 'followup', 'onboarding')";
    }

    $stmt = $pdo->prepare("
        SELECT q.id, q.text, q.type, q.category, q.input_type, q.options_json, q.priority
        FROM ai_questions q
        WHERE q.is_active = 1
              AND (q.frequency != 'once' OR q.id NOT IN (
                  SELECT question_id FROM ai_responses WHERE device_id = ? AND pool = ?
              ))
              $exclude_clause
        ORDER BY $type_order, q.priority DESC
        LIMIT 1
    ");

    $query_params = array_merge([$device_id, $pool], $params);
    $stmt->execute($query_params);
    $question = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$question) {
        // No more questions available
        successResponse([
            'question' => null,
            'message' => 'No more questions available right now'
        ]);
    }

    // Decode options
    if ($question['options_json']) {
        $question['options'] = json_decode($question['options_json'], true);
    }
    unset($question['options_json']);

    // Queue this question
    $stmt = $pdo->prepare("
        INSERT INTO ai_question_queue
        (device_id, question_id, pool, triggered_by, status, expires_at)
        VALUES (?, ?, ?, 'user_request', 'delivered', DATE_ADD(NOW(), INTERVAL 1 DAY))
    ");
    $stmt->execute([$device_id, $question['id'], $pool]);

    $queue_id = $pdo->lastInsertId();
    $question['queue_id'] = $queue_id;

    successResponse([
        'question' => $question
    ]);

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
