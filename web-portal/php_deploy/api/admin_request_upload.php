<?php
/**
 * Admin Request Upload API Endpoint
 * Triggers a device to upload data on next heartbeat
 *
 * POST /api/admin_request_upload.php?device_id=<id>
 * Requires admin session
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/../includes/auth.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

// Require admin authentication
session_start();
if (empty($_SESSION['admin_id'])) {
    errorResponse('Admin authentication required', 401);
}

$device_id = intval($_GET['device_id'] ?? $_POST['device_id'] ?? 0);
if ($device_id <= 0) {
    errorResponse('Missing or invalid device_id');
}

$pdo = db();

try {
    // Verify device exists
    $stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE id = ? AND is_active = 1");
    $stmt->execute([$device_id]);
    $device = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$device) {
        errorResponse('Device not found', 404);
    }

    // Check for existing pending upload command
    $stmt = $pdo->prepare("
        SELECT id FROM device_commands
        WHERE device_id = ? AND command_type = 'upload' AND status IN ('pending', 'acknowledged')
    ");
    $stmt->execute([$device_id]);

    if ($stmt->fetch()) {
        errorResponse('Upload already requested and pending');
    }

    // Create upload command
    $stmt = $pdo->prepare("
        INSERT INTO device_commands (device_id, command_type, payload)
        VALUES (?, 'upload', ?)
    ");
    $payload = json_encode(['reason' => 'admin_request', 'requested_by' => $_SESSION['admin_username'] ?? 'admin']);
    $stmt->execute([$device_id, $payload]);

    $command_id = $pdo->lastInsertId();

    jsonResponse([
        'ok' => true,
        'command_id' => $command_id,
        'message' => 'Upload requested. Device will upload on next heartbeat.'
    ]);

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
