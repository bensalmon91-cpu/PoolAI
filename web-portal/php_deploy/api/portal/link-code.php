<?php
/**
 * Generate Link Code API
 * Called by Pi devices to generate a code for portal linking
 *
 * POST /api/portal/link-code.php
 * Headers: X-API-Key: <device_api_key>
 * Returns: { "ok": true, "code": "ABC-123", "expires_in": 900 }
 */

require_once __DIR__ . '/../../config/config.php';
require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
header('Content-Type: application/json');

// Only allow POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

// Authenticate device
$device = authenticateDevice();
if (!$device) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Invalid API key']);
    exit;
}

$pdo = db();

// Generate 6-character code (A-Z, 0-9, no confusing chars like O, 0, I, 1)
$chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
$code = '';
for ($i = 0; $i < 6; $i++) {
    $code .= $chars[random_int(0, strlen($chars) - 1)];
}

// Code expires in 15 minutes
$expiresMinutes = 15;
$expiresAt = date('Y-m-d H:i:s', strtotime("+{$expiresMinutes} minutes"));

// Update device with link code
$stmt = $pdo->prepare("
    UPDATE pi_devices
    SET link_code = ?, link_code_expires = ?
    WHERE id = ?
");
$stmt->execute([$code, $expiresAt, $device['id']]);

// Format code with dash for display
$formattedCode = substr($code, 0, 3) . '-' . substr($code, 3, 3);

echo json_encode([
    'ok' => true,
    'code' => $formattedCode,
    'raw_code' => $code,
    'expires_at' => $expiresAt,
    'expires_in' => $expiresMinutes * 60
]);
