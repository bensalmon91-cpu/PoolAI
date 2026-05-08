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

setCorsHeaders();

requireMethod('POST');

if (!isAdmin()) {
    errorResponse('Unauthorized', 401);
}

$pdo = db();
$input = getJsonInput();

$device_id = intval($input['device_id'] ?? 0);
$alias = trim($input['alias'] ?? '');

if ($device_id <= 0) {
    errorResponse('Invalid device_id');
}

$stmt = $pdo->prepare("
    UPDATE pi_devices
    SET alias = ?, alias_updated_at = NOW()
    WHERE id = ?
");
$stmt->execute([$alias, $device_id]);

if ($stmt->rowCount() === 0) {
    errorResponse('Device not found', 404);
}

jsonResponse([
    'ok' => true,
    'alias' => $alias,
    'source' => 'admin'
]);
