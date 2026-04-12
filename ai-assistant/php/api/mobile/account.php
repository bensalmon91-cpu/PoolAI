<?php
/**
 * Mobile API: User Account
 *
 * GET   /api/mobile/account.php              - Get account details
 * PATCH /api/mobile/account.php              - Update profile
 * POST  /api/mobile/account.php?action=password  - Change password
 *
 * Headers: Authorization: Bearer <access_token>
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, PATCH, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

require_once __DIR__ . '/../../includes/MobileAuth.php';

$auth = new MobileAuth();
$user = $auth->requireAuth();

switch ($_SERVER['REQUEST_METHOD']) {
    case 'GET':
        echo json_encode([
            'ok' => true,
            'user' => $user
        ]);
        break;

    case 'PATCH':
        $input = json_decode(file_get_contents('php://input'), true);

        if (!$input) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Invalid JSON body']);
            exit;
        }

        $result = $auth->updateProfile($user['id'], $input);
        http_response_code($result['ok'] ? 200 : 400);
        echo json_encode($result);
        break;

    case 'POST':
        $action = $_GET['action'] ?? '';

        if ($action === 'password') {
            $input = json_decode(file_get_contents('php://input'), true);

            $currentPassword = $input['current_password'] ?? '';
            $newPassword = $input['new_password'] ?? '';

            if (empty($currentPassword) || empty($newPassword)) {
                http_response_code(400);
                echo json_encode(['ok' => false, 'error' => 'Current and new password required']);
                exit;
            }

            $result = $auth->changePassword($user['id'], $currentPassword, $newPassword);
            http_response_code($result['ok'] ? 200 : 400);
            echo json_encode($result);
        } else {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Unknown action']);
        }
        break;

    default:
        http_response_code(405);
        echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
}
