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
require_once __DIR__ . '/../includes/AuditLog.php';

setCorsHeaders();

// Audit helper — captures every failed admin attempt with consistent shape.
$auditFail = function(string $result, string $reason, int $deviceId = 0, array $extra = []) {
    $details = array_merge(['reason' => $reason], $extra);
    AuditLog::record(
        'admin',
        'device.command_queue',
        ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
        $deviceId > 0 ? ['type' => 'device', 'id' => (string)$deviceId] : null,
        $result,
        $details
    );
};

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    $auditFail('denied', 'method_not_allowed');
    errorResponse('Method not allowed', 405);
}

// Require admin authentication (uses startSecureSession with correct session name)
if (!isAdmin()) {
    $auditFail('denied', 'not_authenticated');
    errorResponse('Admin authentication required', 401);
}

// Parse input
$input = getJsonInput();
$deviceId = intval($input['device_id'] ?? 0);
$command = trim($input['command'] ?? '');

if ($deviceId <= 0) {
    $auditFail('denied', 'invalid_device_id');
    errorResponse('Missing or invalid device_id');
}

if (empty($command)) {
    $auditFail('denied', 'missing_command', $deviceId);
    errorResponse('Missing command type');
}

// Validate command type
$validCommands = ['upload', 'restart', 'update'];
if (!in_array($command, $validCommands)) {
    $auditFail('denied', 'invalid_command_type', $deviceId, ['command' => $command]);
    errorResponse('Invalid command type. Must be one of: ' . implode(', ', $validCommands));
}

$pdo = db();

try {
    // Verify device exists
    $stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE id = ? AND is_active = 1");
    $stmt->execute([$deviceId]);
    $device = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$device) {
        $auditFail('denied', 'device_not_found', $deviceId, ['command' => $command]);
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
        $auditFail('fail', 'create_command_failed', $deviceId, ['command' => $command, 'error' => $result['error']]);
        errorResponse($result['error']);
    }

    AuditLog::record(
        'admin',
        'device.command_queue',
        ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
        ['type' => 'device', 'id' => (string)$deviceId],
        'ok',
        ['command' => $command, 'command_id' => $result['command_id']]
    );

    jsonResponse([
        'ok' => true,
        'command_id' => $result['command_id'],
        'device_name' => $device['name'] ?: 'Device ' . $device['id'],
        'command_type' => $command,
        'message' => $result['message']
    ]);

} catch (PDOException $e) {
    $auditFail('fail', 'db_error', $deviceId, ['command' => $command, 'error' => $e->getMessage()]);
    error_log("Admin device command error: " . $e->getMessage());
    errorResponse('Database error', 500);
}
