<?php
/**
 * Admin per-device settings update API.
 *
 * POST /api/admin_update_setting.php
 * Body: { "device_id": 123, "settings": { "cloud_upload_enabled": false, ... } }
 *
 * Validates each proposed setting against RemoteSettings::schema() (the
 * allow-list of remotely-editable pooldash settings). Queues an
 * `apply_settings` command on device_commands for the Pi to pick up on
 * its next heartbeat. Returns per-key errors for anything rejected.
 *
 * Secrets / device identity / backend URLs are NOT in the allow-list - those
 * can only be changed via local UI or a signed software update.
 */

declare(strict_types=1);

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AdminDevices.php';
require_once __DIR__ . '/../includes/RemoteSettings.php';
require_once __DIR__ . '/../includes/AuditLog.php';

setCorsHeaders();

$auditFail = function(string $result, string $reason, int $deviceId = 0, array $extra = []) {
    $details = array_merge(['reason' => $reason], $extra);
    AuditLog::record(
        'admin',
        'device.setting_push',
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
if (!isAdmin()) {
    $auditFail('denied', 'not_authenticated');
    errorResponse('Admin authentication required', 401);
}

$pdo = db();

$input = getJsonInput();
$deviceId = (int)($input['device_id'] ?? 0);
$settings = $input['settings'] ?? [];

if ($deviceId <= 0) {
    $auditFail('denied', 'invalid_device_id');
    errorResponse('Missing or invalid device_id');
}
if (!is_array($settings) || empty($settings)) {
    $auditFail('denied', 'no_settings_provided', $deviceId);
    errorResponse('No settings provided');
}

$stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE id = ? AND is_active = 1");
$stmt->execute([$deviceId]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$device) {
    $auditFail('denied', 'device_not_found', $deviceId);
    errorResponse('Device not found', 404);
}

$validation = RemoteSettings::validate($settings);
if (empty($validation['clean'])) {
    $auditFail('denied', 'all_settings_rejected', $deviceId, ['errors' => $validation['errors']]);
    errorResponse('No valid settings in request. Errors: ' . json_encode($validation['errors']), 400);
}

// Queue the command. AdminDevices::createCommand already merges metadata
// (requested_by, requested_at) into the payload.
$adminDevices = new AdminDevices();
$result = $adminDevices->createCommand(
    $deviceId,
    'apply_settings',
    ['settings' => $validation['clean']],
    $_SESSION['admin_username'] ?? 'admin'
);

if (!$result['ok']) {
    $auditFail('fail', 'create_command_failed', $deviceId, ['error' => $result['error'] ?? null]);
    errorResponse($result['error'] ?? 'Could not queue settings command', 500);
}

AuditLog::record(
    'admin',
    'device.setting_push',
    ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
    ['type' => 'device', 'id' => (string)$deviceId],
    'ok',
    [
        'applied_keys' => array_keys($validation['clean']),
        'values' => $validation['clean'],
        'rejected' => $validation['errors'],
        'command_id' => $result['command_id'],
    ]
);

successResponse([
    'command_id' => $result['command_id'],
    'device_name' => $device['name'] ?: ('Device ' . $device['id']),
    'applied_keys' => array_keys($validation['clean']),
    'rejected' => $validation['errors'],
    'message' => 'Settings will apply on the device\'s next heartbeat (~1 minute).',
]);
