<?php
/**
 * Mobile API: Reset Password with Token
 *
 * POST /api/mobile/auth/reset-password
 * Body: { token, password }
 * Response: { ok, message } or { ok: false, error }
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

$token = trim($input['token'] ?? '');
$password = $input['password'] ?? '';

if (empty($token) || empty($password)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Token and password are required']);
    exit;
}

// Reset password
$auth = new MobileAuth();
$result = $auth->resetPassword($token, $password);

http_response_code($result['ok'] ? 200 : 400);
echo json_encode($result);
