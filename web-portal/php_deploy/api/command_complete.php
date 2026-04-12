<?php
/**
 * Device Command Completion API Endpoint
 * Device reports command completion status
 *
 * POST /api/command_complete.php?id=<command_id>
 * Headers: X-API-Key: <device-api-key>
 * Body: JSON with success and result
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

// Get API key
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
$command_id = intval($_GET['id'] ?? 0);

if ($command_id <= 0) {
    errorResponse('Missing or invalid command id');
}

// Get JSON body
$input = getJsonInput();
$success = !empty($input['success']);
$result = $input['result'] ?? null;

$status = $success ? 'completed' : 'failed';

try {
    // Verify command belongs to this device
    $stmt = $pdo->prepare("
        SELECT id FROM device_commands
        WHERE id = ? AND device_id = ?
    ");
    $stmt->execute([$command_id, $device_id]);

    if (!$stmt->fetch()) {
        errorResponse('Command not found', 404);
    }

    // Update command status
    $stmt = $pdo->prepare("
        UPDATE device_commands
        SET status = ?, completed_at = NOW(), result = ?
        WHERE id = ?
    ");
    $stmt->execute([$status, $result, $command_id]);

    jsonResponse(['ok' => true]);

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
