<?php
/**
 * Mobile API: Refresh Access Token
 *
 * POST /api/mobile/auth/refresh
 * Body: { refresh_token }
 * Response: { ok, access_token, expires_in } or { ok: false, error }
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

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

require_once __DIR__ . '/../../../includes/MobileAuth.php';

// Parse JSON body
$input = json_decode(file_get_contents('php://input'), true);
if (!$input) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Invalid JSON body']);
    exit;
}

$refreshToken = trim($input['refresh_token'] ?? '');

if (empty($refreshToken)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Refresh token is required']);
    exit;
}

// Refresh token
$auth = new MobileAuth();
$result = $auth->refresh($refreshToken);

http_response_code($result['ok'] ? 200 : 401);
echo json_encode($result);
