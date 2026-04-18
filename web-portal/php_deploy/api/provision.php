<?php
/**
 * Device provisioning endpoint.
 *
 * POST /api/provision.php
 *
 * Accepts ONE of the following credentials:
 *   X-Bootstrap-Code: <per-device-code>    (preferred - single-use)
 *   X-Bootstrap-Secret: <shared-secret>    (legacy - fleet-wide shared secret)
 *
 * Body (JSON):
 *   {
 *     "device_id":        "<pi-uuid>",       // required
 *     "hostname":         "<string>",        // optional
 *     "model":            "<string>",        // optional
 *     "software_version": "<string>"         // optional
 *   }
 *
 * Returns: { "ok": true, "api_key": "<long-lived>", "device_id": "<echo>" }
 *
 * The legacy shared-secret path is retained for backward compatibility
 * during the Phase 3.3 rollout and can be disabled via env flag
 * `DISABLE_SHARED_BOOTSTRAP=true` once every device has been migrated.
 */

declare(strict_types=1);

require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

setCorsHeaders();
requireMethod('POST');

$pdo = db();

// Ensure bootstrap_codes exists (idempotent; also created by admin UI).
$pdo->exec("CREATE TABLE IF NOT EXISTS bootstrap_codes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code_hash CHAR(64) NOT NULL UNIQUE,
    device_uuid VARCHAR(64) NULL,
    label VARCHAR(200) NOT NULL,
    issued_by_admin_id INT NULL,
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    used_at TIMESTAMP NULL,
    used_ip VARCHAR(64) NULL,
    revoked_at TIMESTAMP NULL,
    revoked_reason TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

$input = getJsonInput();
$deviceUuid = trim((string)($input['device_id'] ?? ''));
$hostname = trim((string)($input['hostname'] ?? ''));
$model = trim((string)($input['model'] ?? ''));
$softwareVersion = trim((string)($input['software_version'] ?? ''));

if ($deviceUuid === '') {
    errorResponse('device_id required');
}

// -----------------------------------------------------------------------
// Credential check: prefer per-device code; fall back to shared secret.
// -----------------------------------------------------------------------
$perDeviceCode = $_SERVER['HTTP_X_BOOTSTRAP_CODE'] ?? '';
$sharedSecret = $_SERVER['HTTP_X_BOOTSTRAP_SECRET'] ?? '';
$clientIp = $_SERVER['REMOTE_ADDR'] ?? '';

$codeRow = null;
$authMode = null;

if ($perDeviceCode !== '') {
    $hash = hash('sha256', trim($perDeviceCode));
    $stmt = $pdo->prepare("
        SELECT id, device_uuid, expires_at, used_at, revoked_at
        FROM bootstrap_codes
        WHERE code_hash = ?
        LIMIT 1
    ");
    $stmt->execute([$hash]);
    $codeRow = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$codeRow) {
        errorResponse('Invalid bootstrap code', 401);
    }
    if ($codeRow['revoked_at']) {
        errorResponse('Bootstrap code has been revoked', 401);
    }
    if ($codeRow['used_at']) {
        // Single-use. If the same device is re-provisioning, we could
        // allow a repeat - but safer to require a fresh code.
        errorResponse('Bootstrap code has already been used', 401);
    }
    if ($codeRow['expires_at'] && strtotime($codeRow['expires_at']) < time()) {
        errorResponse('Bootstrap code has expired', 401);
    }
    $authMode = 'code';
} elseif ($sharedSecret !== '') {
    $sharedDisabled = (bool)env('DISABLE_SHARED_BOOTSTRAP', false);
    if ($sharedDisabled) {
        errorResponse('Shared bootstrap secret disabled; use a per-device code', 401);
    }
    $expected = (string)(defined('BOOTSTRAP_SECRET') ? BOOTSTRAP_SECRET : env('BOOTSTRAP_SECRET', ''));
    if ($expected === '' || !hash_equals($expected, trim($sharedSecret))) {
        errorResponse('Invalid bootstrap secret', 401);
    }
    $authMode = 'shared';
} else {
    errorResponse('Missing bootstrap credential (X-Bootstrap-Code or X-Bootstrap-Secret)', 401);
}

// -----------------------------------------------------------------------
// Provision / update device row. Generate a new api_key every time so a
// re-provisioned device invalidates the prior key.
// -----------------------------------------------------------------------
$apiKey = bin2hex(random_bytes(32));

try {
    $pdo->beginTransaction();

    $stmt = $pdo->prepare("SELECT id FROM pi_devices WHERE device_uuid = ?");
    $stmt->execute([$deviceUuid]);
    $existing = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($existing) {
        $upd = $pdo->prepare("
            UPDATE pi_devices
            SET api_key = ?, is_active = 1, last_seen = NOW()
            WHERE id = ?
        ");
        $upd->execute([$apiKey, $existing['id']]);
        $deviceRowId = (int)$existing['id'];
    } else {
        $ins = $pdo->prepare("
            INSERT INTO pi_devices (device_uuid, name, api_key, is_active, last_seen)
            VALUES (?, ?, ?, 1, NOW())
        ");
        $ins->execute([$deviceUuid, $hostname !== '' ? $hostname : null, $apiKey]);
        $deviceRowId = (int)$pdo->lastInsertId();
    }

    if ($authMode === 'code' && $codeRow) {
        $mark = $pdo->prepare("
            UPDATE bootstrap_codes
            SET used_at = NOW(), used_ip = ?, device_uuid = ?
            WHERE id = ? AND used_at IS NULL
        ");
        $mark->execute([$clientIp, $deviceUuid, (int)$codeRow['id']]);
    }

    $pdo->commit();
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    error_log('provision.php: ' . $e->getMessage());
    errorResponse('Provisioning failed', 500);
}

successResponse([
    'api_key' => $apiKey,
    'device_id' => $deviceUuid,
    'auth_mode' => $authMode,
    'server_version' => 'provision-v2',
]);
