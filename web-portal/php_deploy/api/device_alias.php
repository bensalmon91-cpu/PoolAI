<?php
/**
 * Device Alias API (Pi-side)
 *
 * POST: Sync device alias from Pi
 *   Header: X-API-Key or Authorization: Bearer
 *   Body: { alias: "Pool Name", alias_updated_at: "2026-03-07T12:00:00Z" }
 *   Response: { ok: true, alias, alias_updated_at, source: "server|device|none" }
 *
 * GET: Pi fetches its current server-side alias
 *   Header: X-API-Key or Authorization: Bearer
 *   Response: { ok: true, alias, alias_updated_at }
 *
 * Admin-side updates use the parallel endpoint on admin.modprojects.co.uk
 * (admin-session auth) — kept separate so each domain has a single auth concern.
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

setCorsHeaders();

$pdo = db();

$api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (empty($api_key)) {
    $auth_header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (stripos($auth_header, 'Bearer ') === 0) {
        $api_key = substr($auth_header, 7);
    }
}

if (empty($api_key)) {
    errorResponse('API key required', 401);
}

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $stmt = $pdo->prepare("SELECT id, alias, alias_updated_at FROM pi_devices WHERE api_key = ? AND is_active = 1");
    $stmt->execute([$api_key]);
    $device = $stmt->fetch();

    if (!$device) {
        errorResponse('Invalid API key', 401);
    }

    jsonResponse([
        'ok' => true,
        'alias' => $device['alias'] ?? '',
        'alias_updated_at' => $device['alias_updated_at'] ?? null
    ]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $input = getJsonInput();

    $stmt = $pdo->prepare("SELECT id, alias, alias_updated_at FROM pi_devices WHERE api_key = ? AND is_active = 1");
    $stmt->execute([$api_key]);
    $device = $stmt->fetch();

    if (!$device) {
        errorResponse('Invalid API key', 401);
    }

    $device_alias = trim($input['alias'] ?? '');
    $device_updated_at = $input['alias_updated_at'] ?? null;

    $device_ts = $device_updated_at ? strtotime($device_updated_at) : 0;
    $server_ts = $device['alias_updated_at'] ? strtotime($device['alias_updated_at']) : 0;

    if ($device_ts > $server_ts && !empty($device_alias)) {
        $stmt = $pdo->prepare("
            UPDATE pi_devices
            SET alias = ?, alias_updated_at = ?
            WHERE id = ?
        ");
        $stmt->execute([
            $device_alias,
            date('Y-m-d H:i:s', $device_ts),
            $device['id']
        ]);

        jsonResponse([
            'ok' => true,
            'alias' => $device_alias,
            'alias_updated_at' => date('c', $device_ts),
            'source' => 'device'
        ]);
    } else if ($server_ts > 0) {
        jsonResponse([
            'ok' => true,
            'alias' => $device['alias'] ?? '',
            'alias_updated_at' => $device['alias_updated_at'] ? date('c', strtotime($device['alias_updated_at'])) : null,
            'source' => 'server'
        ]);
    } else {
        jsonResponse([
            'ok' => true,
            'alias' => '',
            'alias_updated_at' => null,
            'source' => 'none'
        ]);
    }
}

errorResponse('Method not allowed', 405);
