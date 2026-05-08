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

setCorsHeaders();
requireAdmin();
requireMethod('POST');

$pdo = db();

$input = getJsonInput();
$deviceId = (int)($input['device_id'] ?? 0);
$settings = $input['settings'] ?? [];

if ($deviceId <= 0) {
    errorResponse('Missing or invalid device_id');
}
if (!is_array($settings) || empty($settings)) {
    errorResponse('No settings provided');
}

$stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE id = ? AND is_active = 1");
$stmt->execute([$deviceId]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$device) {
    errorResponse('Device not found', 404);
}

$validation = RemoteSettings::validate($settings);
if (empty($validation['clean'])) {
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
    errorResponse($result['error'] ?? 'Could not queue settings command', 500);
}

successResponse([
    'command_id' => $result['command_id'],
    'device_name' => $device['name'] ?: ('Device ' . $device['id']),
    'applied_keys' => array_keys($validation['clean']),
    'rejected' => $validation['errors'],
    'message' => 'Settings will apply on the device\'s next heartbeat (~1 minute).',
]);
