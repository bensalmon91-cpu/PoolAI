<?php
/**
 * Mobile API: Logout
 *
 * POST /api/mobile/auth/logout
 * Headers: Authorization: Bearer <access_token>
 * Body: { refresh_token }
 * Response: { ok }
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

require_once __DIR__ . '/../../../includes/MobileAuth.php';

$auth = new MobileAuth();

// Require authentication
$user = $auth->requireAuth();

// Parse JSON body
$input = json_decode(file_get_contents('php://input'), true);
$refreshToken = trim($input['refresh_token'] ?? '');

if (!empty($refreshToken)) {
    $result = $auth->logout($refreshToken, $user['id']);
} else {
    // If no refresh token provided, just acknowledge logout
    $result = ['ok' => true];
}

echo json_encode($result);
