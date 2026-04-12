<?php
/**
 * AI Suggestion Feedback API - Device endpoint for suggestion actions
 *
 * POST /api/ai/suggestion_feedback.php
 * Headers: X-API-Key: <device-api-key>
 * Body: { suggestion_id, action: "read|acted_upon|dismissed", feedback? }
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
if (empty($input['suggestion_id'])) {
    errorResponse('Missing suggestion_id');
}
if (empty($input['action'])) {
    errorResponse('Missing action');
}

$valid_actions = ['read', 'acted_upon', 'dismissed'];
if (!in_array($input['action'], $valid_actions)) {
    errorResponse('Invalid action. Must be one of: ' . implode(', ', $valid_actions));
}

try {
    // Get suggestion and verify it belongs to this device
    $stmt = $pdo->prepare("
        SELECT id, status FROM ai_suggestions
        WHERE id = ? AND device_id = ?
    ");
    $stmt->execute([$input['suggestion_id'], $device_id]);
    $suggestion = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$suggestion) {
        errorResponse('Suggestion not found or does not belong to this device', 404);
    }

    // Update suggestion based on action
    $updates = ['status = ?'];
    $params = [$input['action']];

    if ($input['action'] === 'read' && $suggestion['status'] === 'delivered') {
        $updates[] = 'read_at = NOW()';
    }

    if (!empty($input['feedback'])) {
        $updates[] = 'user_feedback = ?';
        $params[] = $input['feedback'];
    }

    if (!empty($input['user_action'])) {
        $updates[] = 'user_action = ?';
        $params[] = $input['user_action'];
    }

    $params[] = $input['suggestion_id'];

    $stmt = $pdo->prepare("
        UPDATE ai_suggestions
        SET " . implode(', ', $updates) . "
        WHERE id = ?
    ");
    $stmt->execute($params);

    successResponse([], 'Feedback recorded');

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
