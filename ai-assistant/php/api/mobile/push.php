<?php
/**
 * Mobile API: Push Token Management
 *
 * POST   /api/mobile/push.php              - Register push token
 * DELETE /api/mobile/push.php              - Unregister push token
 * GET    /api/mobile/push.php?history=1    - Get notification history
 * POST   /api/mobile/push.php?action=read&id=X - Mark notification as read
 *
 * Headers: Authorization: Bearer <access_token>
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

require_once __DIR__ . '/../../includes/MobileAuth.php';
require_once __DIR__ . '/../../includes/PushNotifications.php';

$auth = new MobileAuth();
$user = $auth->requireAuth();

$push = new PushNotifications();

switch ($_SERVER['REQUEST_METHOD']) {
    case 'GET':
        // Get notification history
        if (isset($_GET['history'])) {
            $limit = isset($_GET['limit']) ? min(100, max(1, (int)$_GET['limit'])) : 50;
            $history = $push->getNotificationHistory($user['id'], $limit);

            echo json_encode([
                'ok' => true,
                'notifications' => $history
            ]);
        } else {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Invalid request']);
        }
        break;

    case 'POST':
        $input = json_decode(file_get_contents('php://input'), true);

        // Check for mark as read action
        if (isset($_GET['action']) && $_GET['action'] === 'read') {
            $notificationId = isset($_GET['id']) ? (int)$_GET['id'] : 0;

            if (!$notificationId) {
                http_response_code(400);
                echo json_encode(['ok' => false, 'error' => 'Notification ID required']);
                exit;
            }

            $success = $push->markAsRead($notificationId, $user['id']);
            echo json_encode(['ok' => $success]);
            break;
        }

        // Register push token
        $fcmToken = trim($input['fcm_token'] ?? '');
        $platform = strtolower(trim($input['platform'] ?? ''));
        $deviceInfo = trim($input['device_info'] ?? '');

        if (empty($fcmToken)) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'FCM token is required']);
            exit;
        }

        if (!in_array($platform, ['ios', 'android'])) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Platform must be "ios" or "android"']);
            exit;
        }

        $result = $push->registerToken($user['id'], $fcmToken, $platform, $deviceInfo);
        http_response_code($result['ok'] ? 200 : 400);
        echo json_encode($result);
        break;

    case 'DELETE':
        $input = json_decode(file_get_contents('php://input'), true);
        $fcmToken = trim($input['fcm_token'] ?? '');

        if (empty($fcmToken)) {
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'FCM token is required']);
            exit;
        }

        $result = $push->unregisterToken($fcmToken);
        echo json_encode($result);
        break;

    default:
        http_response_code(405);
        echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
}
