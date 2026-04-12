<?php
/**
 * Mobile API: User Login
 *
 * POST /api/mobile/auth/login
 * Body: { email, password, platform: "ios"|"android", device_info? }
 * Response: { ok, access_token, refresh_token, expires_in, user } or { ok: false, error }
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

// Validate required fields
$email = trim($input['email'] ?? '');
$password = $input['password'] ?? '';
$platform = strtolower(trim($input['platform'] ?? ''));

if (empty($email) || empty($password)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Email and password are required']);
    exit;
}

// Validate platform
if (!in_array($platform, ['ios', 'android'])) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Platform must be "ios" or "android"']);
    exit;
}

$deviceInfo = trim($input['device_info'] ?? '');

// Login user
$auth = new MobileAuth();
$result = $auth->login($email, $password, $platform, $deviceInfo);

if ($result['ok']) {
    http_response_code(200);
} else {
    // Check for unverified email (special case)
    if (isset($result['unverified']) && $result['unverified']) {
        http_response_code(403);
    } else {
        http_response_code(401);
    }
}

echo json_encode($result);
