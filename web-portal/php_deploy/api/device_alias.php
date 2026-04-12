<?php
/**
 * Device Alias API
 *
 * POST (admin): Update device alias from admin panel
 *   Body: { device_id: 123, alias: "Pool Name" }
 *
 * POST (device): Sync device alias from Pi
 *   Header: X-API-Key or Authorization: Bearer
 *   Body: { alias: "Pool Name", alias_updated_at: "2026-03-07T12:00:00Z" }
 *   Response: { ok: true, alias: "...", alias_updated_at: "...", source: "server|device" }
 *
 * GET (device): Get current alias from server
 *   Header: X-API-Key or Authorization: Bearer
 *   Response: { alias: "...", alias_updated_at: "..." }
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';
require_once __DIR__ . '/../includes/auth.php';

setCorsHeaders();

$pdo = db();

// Check authentication method
$api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (empty($api_key)) {
    $auth_header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (stripos($auth_header, 'Bearer ') === 0) {
        $api_key = substr($auth_header, 7);
    }
}

$is_device_auth = !empty($api_key);
$is_admin_auth = isAdmin();

// GET - Device fetching its alias
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    if (!$is_device_auth) {
        errorResponse('API key required', 401);
    }

    // Get device by API key
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

// POST - Update alias
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $input = getJsonInput();

    // Admin updating via admin panel
    if ($is_admin_auth && isset($input['device_id'])) {
        $device_id = intval($input['device_id']);
        $alias = trim($input['alias'] ?? '');

        if ($device_id <= 0) {
            errorResponse('Invalid device_id');
        }

        // Update alias with current timestamp
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
    }

    // Device syncing its alias
    if ($is_device_auth) {
        // Get device
        $stmt = $pdo->prepare("SELECT id, alias, alias_updated_at FROM pi_devices WHERE api_key = ? AND is_active = 1");
        $stmt->execute([$api_key]);
        $device = $stmt->fetch();

        if (!$device) {
            errorResponse('Invalid API key', 401);
        }

        $device_alias = trim($input['alias'] ?? '');
        $device_updated_at = $input['alias_updated_at'] ?? null;

        // Convert device timestamp to comparable format
        $device_ts = $device_updated_at ? strtotime($device_updated_at) : 0;
        $server_ts = $device['alias_updated_at'] ? strtotime($device['alias_updated_at']) : 0;

        // Latest change wins
        if ($device_ts > $server_ts && !empty($device_alias)) {
            // Device has newer alias - update server
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
            // Server has newer or same alias - return server value
            jsonResponse([
                'ok' => true,
                'alias' => $device['alias'] ?? '',
                'alias_updated_at' => $device['alias_updated_at'] ? date('c', strtotime($device['alias_updated_at'])) : null,
                'source' => 'server'
            ]);
        } else {
            // No alias set anywhere
            jsonResponse([
                'ok' => true,
                'alias' => '',
                'alias_updated_at' => null,
                'source' => 'none'
            ]);
        }
    }

    errorResponse('Authentication required', 401);
}

errorResponse('Method not allowed', 405);
