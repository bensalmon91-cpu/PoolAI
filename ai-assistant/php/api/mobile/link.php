<?php
/**
 * Mobile API: Link Device
 *
 * POST /api/mobile/link.php
 * Headers: Authorization: Bearer <access_token>
 * Body: { code: "ABC123" }
 * Response: { ok, device } or { ok: false, error }
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

require_once __DIR__ . '/../../includes/MobileAuth.php';
require_once __DIR__ . '/../../includes/MobileDevices.php';

$auth = new MobileAuth();
$user = $auth->requireAuth();

$input = json_decode(file_get_contents('php://input'), true);
$code = trim($input['code'] ?? '');

if (empty($code)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Link code is required']);
    exit;
}

$devices = new MobileDevices($user['id']);
$result = $devices->linkDevice($code);

http_response_code($result['ok'] ? 200 : 400);
echo json_encode($result);
