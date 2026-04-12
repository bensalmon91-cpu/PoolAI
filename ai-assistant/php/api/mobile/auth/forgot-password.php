<?php
/**
 * Mobile API: Request Password Reset
 *
 * POST /api/mobile/auth/forgot-password
 * Body: { email }
 * Response: { ok, message }
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

$email = trim($input['email'] ?? '');

if (empty($email)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Email is required']);
    exit;
}

// Request password reset
$auth = new MobileAuth();
$result = $auth->requestPasswordReset($email);

// Always return 200 to prevent email enumeration
echo json_encode($result);
