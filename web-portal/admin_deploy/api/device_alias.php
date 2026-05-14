<?php
/**
 * Device Alias API (admin-side)
 *
 * POST: Update device alias from admin panel
 *   Auth: admin session (isAdmin())
 *   Body: { device_id: 123, alias: "Pool Name" }
 *
 * Pi devices use the parallel endpoint on poolaissistant.modprojects.co.uk
 * (api-key auth) — kept separate so each domain has a single auth concern.
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AuditLog.php';

setCorsHeaders();

$auditFail = function(string $result, string $reason, int $deviceId = 0, array $extra = []) {
    AuditLog::record(
        'admin',
        'device.alias_change',
        ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
        $deviceId > 0 ? ['type' => 'device', 'id' => (string)$deviceId] : null,
        $result,
        array_merge(['reason' => $reason], $extra)
    );
};

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    $auditFail('denied', 'method_not_allowed');
    errorResponse('Method not allowed', 405);
}

if (!isAdmin()) {
    $auditFail('denied', 'not_authenticated');
    errorResponse('Unauthorized', 401);
}

$pdo = db();
$input = getJsonInput();

$device_id = intval($input['device_id'] ?? 0);
$alias = trim($input['alias'] ?? '');

if ($device_id <= 0) {
    $auditFail('denied', 'invalid_device_id');
    errorResponse('Invalid device_id');
}

// Capture the old alias so the audit row shows the diff.
$prevStmt = $pdo->prepare("SELECT alias FROM pi_devices WHERE id = ?");
$prevStmt->execute([$device_id]);
$prev = $prevStmt->fetch();
$oldAlias = $prev ? ($prev['alias'] ?? '') : null;

$stmt = $pdo->prepare("
    UPDATE pi_devices
    SET alias = ?, alias_updated_at = NOW()
    WHERE id = ?
");
$stmt->execute([$alias, $device_id]);

if ($stmt->rowCount() === 0 && $prev === false) {
    $auditFail('denied', 'device_not_found', $device_id);
    errorResponse('Device not found', 404);
}

AuditLog::record(
    'admin',
    'device.alias_change',
    ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
    ['type' => 'device', 'id' => (string)$device_id],
    'ok',
    ['old' => $oldAlias, 'new' => $alias]
);

jsonResponse([
    'ok' => true,
    'alias' => $alias,
    'source' => 'admin'
]);
