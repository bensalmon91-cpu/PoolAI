<?php
/**
 * PoolAIssistant Push Notifications
 *
 * Handles Firebase Cloud Messaging (FCM) for iOS and Android push notifications.
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../config/config.php';

class PushNotifications {
    private $pdo;
    private $fcmServerKey;
    private $fcmEndpoint = 'https://fcm.googleapis.com/fcm/send';

    public function __construct() {
        $this->pdo = db();
        $this->fcmServerKey = env('FCM_SERVER_KEY', '');
    }

    /**
     * Register a push token for a user
     */
    public function registerToken(int $userId, string $fcmToken, string $platform, string $deviceInfo = ''): array {
        if (!in_array($platform, ['ios', 'android'])) {
            return ['ok' => false, 'error' => 'Invalid platform'];
        }

        if (empty($fcmToken)) {
            return ['ok' => false, 'error' => 'FCM token is required'];
        }

        try {
            // Upsert token
            $stmt = $this->pdo->prepare("
                INSERT INTO push_tokens (user_id, fcm_token, platform, device_info)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    user_id = VALUES(user_id),
                    platform = VALUES(platform),
                    device_info = VALUES(device_info),
                    is_active = 1,
                    updated_at = NOW()
            ");
            $stmt->execute([$userId, $fcmToken, $platform, $deviceInfo]);

            return ['ok' => true];
        } catch (PDOException $e) {
            error_log("Push token registration error: " . $e->getMessage());
            return ['ok' => false, 'error' => 'Failed to register token'];
        }
    }

    /**
     * Unregister a push token
     */
    public function unregisterToken(string $fcmToken): array {
        $stmt = $this->pdo->prepare("DELETE FROM push_tokens WHERE fcm_token = ?");
        $stmt->execute([$fcmToken]);

        return ['ok' => true];
    }

    /**
     * Mark token as inactive (for invalid tokens reported by FCM)
     */
    public function deactivateToken(string $fcmToken): void {
        $stmt = $this->pdo->prepare("UPDATE push_tokens SET is_active = 0 WHERE fcm_token = ?");
        $stmt->execute([$fcmToken]);
    }

    /**
     * Get all active tokens for a user
     */
    public function getUserTokens(int $userId): array {
        $stmt = $this->pdo->prepare("
            SELECT fcm_token, platform, device_info
            FROM push_tokens
            WHERE user_id = ? AND is_active = 1
        ");
        $stmt->execute([$userId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Send notification to a user
     */
    public function sendToUser(int $userId, string $title, string $body, string $type, ?int $deviceId = null, array $data = []): array {
        $tokens = $this->getUserTokens($userId);

        if (empty($tokens)) {
            return ['ok' => false, 'error' => 'No registered devices'];
        }

        // Check notification preferences
        if (!$this->shouldNotify($userId, $type, $deviceId)) {
            return ['ok' => false, 'error' => 'User has disabled this notification type'];
        }

        $results = [];
        $success = 0;

        foreach ($tokens as $token) {
            $result = $this->send($token['fcm_token'], $title, $body, $data, $token['platform']);

            if ($result['ok']) {
                $success++;
            } elseif (isset($result['invalid_token']) && $result['invalid_token']) {
                $this->deactivateToken($token['fcm_token']);
            }

            $results[] = $result;
        }

        // Log notification
        $this->logNotification($userId, $deviceId, $type, $title, $body, $data);

        return [
            'ok' => $success > 0,
            'sent' => $success,
            'total' => count($tokens),
            'results' => $results
        ];
    }

    /**
     * Send notification to multiple users (e.g., all users linked to a device)
     */
    public function sendToDeviceUsers(int $deviceId, string $title, string $body, string $type, array $data = []): array {
        // Get all users linked to this device
        $stmt = $this->pdo->prepare("
            SELECT DISTINCT user_id FROM user_devices WHERE device_id = ?
        ");
        $stmt->execute([$deviceId]);
        $users = $stmt->fetchAll(PDO::FETCH_COLUMN);

        $results = [];
        foreach ($users as $userId) {
            $results[$userId] = $this->sendToUser($userId, $title, $body, $type, $deviceId, $data);
        }

        return $results;
    }

    /**
     * Send raw FCM notification
     */
    private function send(string $fcmToken, string $title, string $body, array $data = [], string $platform = 'android'): array {
        if (empty($this->fcmServerKey)) {
            return ['ok' => false, 'error' => 'FCM server key not configured'];
        }

        $notification = [
            'title' => $title,
            'body' => $body,
            'sound' => 'default'
        ];

        // iOS-specific settings
        if ($platform === 'ios') {
            $notification['badge'] = 1;
        }

        $payload = [
            'to' => $fcmToken,
            'notification' => $notification,
            'data' => array_merge($data, [
                'click_action' => 'FLUTTER_NOTIFICATION_CLICK'
            ]),
            'priority' => 'high'
        ];

        $headers = [
            'Authorization: key=' . $this->fcmServerKey,
            'Content-Type: application/json'
        ];

        $ch = curl_init();
        curl_setopt_array($ch, [
            CURLOPT_URL => $this->fcmEndpoint,
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_POSTFIELDS => json_encode($payload),
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 10
        ]);

        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = curl_error($ch);
        curl_close($ch);

        if ($error) {
            return ['ok' => false, 'error' => $error];
        }

        $result = json_decode($response, true);

        if ($httpCode !== 200) {
            return ['ok' => false, 'error' => 'FCM error: ' . $httpCode];
        }

        if (isset($result['results'][0]['error'])) {
            $errorCode = $result['results'][0]['error'];
            $invalidTokenErrors = ['InvalidRegistration', 'NotRegistered', 'MismatchSenderId'];

            return [
                'ok' => false,
                'error' => $errorCode,
                'invalid_token' => in_array($errorCode, $invalidTokenErrors)
            ];
        }

        return ['ok' => true, 'message_id' => $result['results'][0]['message_id'] ?? null];
    }

    /**
     * Check if user should receive this notification type
     */
    private function shouldNotify(int $userId, string $type, ?int $deviceId): bool {
        // Get user's notification preferences
        $stmt = $this->pdo->prepare("
            SELECT * FROM user_notification_prefs
            WHERE user_id = ? AND (device_id IS NULL OR device_id = ?)
            ORDER BY device_id DESC
            LIMIT 1
        ");
        $stmt->execute([$userId, $deviceId]);
        $prefs = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$prefs) {
            // Default to allowing all notifications
            return true;
        }

        // Map notification types to preference columns
        $typeMap = [
            'alarm' => 'notify_alarms',
            'suggestion' => 'notify_suggestions',
            'device_offline' => 'notify_device_offline',
            'maintenance' => 'notify_maintenance_due'
        ];

        if (isset($typeMap[$type]) && isset($prefs[$typeMap[$type]])) {
            if (!$prefs[$typeMap[$type]]) {
                return false;
            }
        }

        // Check quiet hours
        if ($prefs['quiet_hours_start'] && $prefs['quiet_hours_end']) {
            $now = new DateTime();
            $start = DateTime::createFromFormat('H:i:s', $prefs['quiet_hours_start']);
            $end = DateTime::createFromFormat('H:i:s', $prefs['quiet_hours_end']);

            if ($start && $end) {
                $nowTime = $now->format('H:i:s');

                // Handle overnight quiet hours (e.g., 22:00 to 07:00)
                if ($start > $end) {
                    if ($nowTime >= $start->format('H:i:s') || $nowTime <= $end->format('H:i:s')) {
                        return false;
                    }
                } else {
                    if ($nowTime >= $start->format('H:i:s') && $nowTime <= $end->format('H:i:s')) {
                        return false;
                    }
                }
            }
        }

        return true;
    }

    /**
     * Log notification to database
     */
    private function logNotification(int $userId, ?int $deviceId, string $type, string $title, string $body, array $data): void {
        try {
            $stmt = $this->pdo->prepare("
                INSERT INTO push_notifications (user_id, device_id, type, title, body, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
            ");
            $stmt->execute([
                $userId,
                $deviceId,
                $type,
                $title,
                $body,
                !empty($data) ? json_encode($data) : null
            ]);
        } catch (PDOException $e) {
            error_log("Failed to log notification: " . $e->getMessage());
        }
    }

    /**
     * Get notification history for a user
     */
    public function getNotificationHistory(int $userId, int $limit = 50): array {
        $stmt = $this->pdo->prepare("
            SELECT id, device_id, type, title, body, sent_at, read_at
            FROM push_notifications
            WHERE user_id = ?
            ORDER BY sent_at DESC
            LIMIT ?
        ");
        $stmt->execute([$userId, $limit]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Mark notification as read
     */
    public function markAsRead(int $notificationId, int $userId): bool {
        $stmt = $this->pdo->prepare("
            UPDATE push_notifications
            SET read_at = NOW()
            WHERE id = ? AND user_id = ? AND read_at IS NULL
        ");
        $stmt->execute([$notificationId, $userId]);
        return $stmt->rowCount() > 0;
    }

    // =========================================================================
    // Notification Trigger Methods (called from other parts of the system)
    // =========================================================================

    /**
     * Send alarm notification
     */
    public function notifyAlarm(int $deviceId, string $alarmType, string $message, string $severity = 'warning'): array {
        $title = $severity === 'critical' ? 'Critical Alarm' : 'Pool Alert';
        $body = $message;

        return $this->sendToDeviceUsers($deviceId, $title, $body, 'alarm', [
            'type' => 'alarm',
            'alarm_type' => $alarmType,
            'severity' => $severity,
            'device_id' => $deviceId
        ]);
    }

    /**
     * Send suggestion notification
     */
    public function notifySuggestion(int $deviceId, int $suggestionId, string $title, string $preview): array {
        return $this->sendToDeviceUsers($deviceId, 'New Suggestion', $preview, 'suggestion', [
            'type' => 'suggestion',
            'suggestion_id' => $suggestionId,
            'device_id' => $deviceId
        ]);
    }

    /**
     * Send device offline notification
     */
    public function notifyDeviceOffline(int $deviceId, string $deviceName, int $offlineMinutes): array {
        $title = 'Device Offline';
        $body = "$deviceName has been offline for $offlineMinutes minutes";

        return $this->sendToDeviceUsers($deviceId, $title, $body, 'device_offline', [
            'type' => 'device_offline',
            'device_id' => $deviceId,
            'offline_minutes' => $offlineMinutes
        ]);
    }

    /**
     * Send maintenance due notification
     */
    public function notifyMaintenanceDue(int $deviceId, string $maintenanceType, string $message): array {
        $title = 'Maintenance Due';

        return $this->sendToDeviceUsers($deviceId, $title, $message, 'maintenance', [
            'type' => 'maintenance',
            'maintenance_type' => $maintenanceType,
            'device_id' => $deviceId
        ]);
    }
}
