<?php
/**
 * Mobile API: User Registration
 *
 * POST /api/mobile/auth/register
 * Body: { email, password, name?, company? }
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

// Validate required fields
$email = trim($input['email'] ?? '');
$password = $input['password'] ?? '';

if (empty($email) || empty($password)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Email and password are required']);
    exit;
}

$name = trim($input['name'] ?? '');
$company = trim($input['company'] ?? '');

// Register user
$auth = new MobileAuth();
$result = $auth->register($email, $password, $name, $company);

http_response_code($result['ok'] ? 201 : 400);
echo json_encode($result);
