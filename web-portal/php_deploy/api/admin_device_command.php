<?php
/**
 * Admin Device Command API Endpoint
 * Creates commands in device_commands table for Pi devices to pick up
 *
 * POST /api/admin_device_command.php
 * Body: { "device_id": 1, "command": "upload|restart|update" }
 *
 * Requires admin session
 *
 * Commands:
 * - upload: Force immediate data upload (runs chunk_manager.py --force-retry)
 * - restart: Restart Pi services (restarts poolaissistant_logger)
 * - update: Check for software updates (runs update_check.py)
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AdminDevices.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

// Require admin authentication (uses startSecureSession with correct session name)
if (!isAdmin()) {
    errorResponse('Admin authentication required', 401);
}

// Parse input
$input = getJsonInput();
$deviceId = intval($input['device_id'] ?? 0);
$command = trim($input['command'] ?? '');

if ($deviceId <= 0) {
    errorResponse('Missing or invalid device_id');
}

if (empty($command)) {
    errorResponse('Missing command type');
}

// Validate command type
$validCommands = ['upload', 'restart', 'update'];
if (!in_array($command, $validCommands)) {
    errorResponse('Invalid command type. Must be one of: ' . implode(', ', $validCommands));
}

$pdo = db();

try {
    // Verify device exists
    $stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE id = ? AND is_active = 1");
    $stmt->execute([$deviceId]);
    $device = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$device) {
        errorResponse('Device not found', 404);
    }

    // Create command using service class
    $adminDevices = new AdminDevices();
    $result = $adminDevices->createCommand(
        $deviceId,
        $command,
        ['reason' => 'admin_panel'],
        $_SESSION['admin_username'] ?? 'admin'
    );

    if (!$result['ok']) {
        errorResponse($result['error']);
    }

    jsonResponse([
        'ok' => true,
        'command_id' => $result['command_id'],
        'device_name' => $device['name'] ?: 'Device ' . $device['id'],
        'command_type' => $command,
        'message' => $result['message']
    ]);

} catch (PDOException $e) {
    error_log("Admin device command error: " . $e->getMessage());
    errorResponse('Database error', 500);
}
