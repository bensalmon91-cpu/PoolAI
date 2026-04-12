<?php
/**
 * PoolAIssistant Portal Device Management
 */

require_once __DIR__ . '/../config/portal.php';
require_once __DIR__ . '/../config/database.php';

class PortalDevices {
    private $pdo;
    private $userId;

    public function __construct($userId) {
        $this->pdo = db();
        $this->userId = $userId;
    }

    /**
     * Get all devices linked to this user
     */
    public function getDevices() {
        $stmt = $this->pdo->prepare("
            SELECT
                ud.id as link_id,
                ud.nickname,
                ud.role,
                ud.linked_at,
                d.id as device_id,
                d.device_uuid,
                d.name as alias,
                d.last_seen,
                h.ip_address,
                h.software_version,
                CASE
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 20 MINUTE) THEN 'online'
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 'away'
                    ELSE 'offline'
                END as status
            FROM user_devices ud
            JOIN pi_devices d ON ud.device_id = d.id
            LEFT JOIN (
                SELECT device_id, ip_address, software_version
                FROM device_health h1
                WHERE ts = (SELECT MAX(ts) FROM device_health h2 WHERE h2.device_id = h1.device_id)
            ) h ON h.device_id = d.id
            WHERE ud.user_id = ?
            ORDER BY ud.linked_at DESC
        ");
        $stmt->execute([$this->userId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get a single device if user has access
     */
    public function getDevice($deviceId) {
        $stmt = $this->pdo->prepare("
            SELECT
                ud.id as link_id,
                ud.nickname,
                ud.role,
                ud.linked_at,
                d.id as device_id,
                d.device_uuid,
                d.name as alias,
                d.last_seen,
                h.ip_address,
                h.software_version,
                CASE
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 20 MINUTE) THEN 'online'
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 'away'
                    ELSE 'offline'
                END as status
            FROM user_devices ud
            JOIN pi_devices d ON ud.device_id = d.id
            LEFT JOIN (
                SELECT device_id, ip_address, software_version
                FROM device_health h1
                WHERE ts = (SELECT MAX(ts) FROM device_health h2 WHERE h2.device_id = h1.device_id)
            ) h ON h.device_id = d.id
            WHERE ud.user_id = ? AND d.id = ?
        ");
        $stmt->execute([$this->userId, $deviceId]);
        return $stmt->fetch(PDO::FETCH_ASSOC);
    }

    /**
     * Link a device using link code
     */
    public function linkDevice($linkCode) {
        $linkCode = strtoupper(trim($linkCode));

        // Remove any dashes/spaces
        $linkCode = preg_replace('/[^A-Z0-9]/', '', $linkCode);

        if (strlen($linkCode) !== 6) {
            return ['ok' => false, 'error' => 'Invalid link code format'];
        }

        // Find device with this link code
        $stmt = $this->pdo->prepare("
            SELECT id, name, device_uuid
            FROM pi_devices
            WHERE link_code = ? AND link_code_expires > NOW()
        ");
        $stmt->execute([$linkCode]);
        $device = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$device) {
            return ['ok' => false, 'error' => 'Invalid or expired link code'];
        }

        // Check if already linked
        $stmt = $this->pdo->prepare("
            SELECT id FROM user_devices
            WHERE user_id = ? AND device_id = ?
        ");
        $stmt->execute([$this->userId, $device['id']]);
        if ($stmt->fetch()) {
            return ['ok' => false, 'error' => 'This device is already linked to your account'];
        }

        // Create link
        $stmt = $this->pdo->prepare("
            INSERT INTO user_devices (user_id, device_id, role, nickname)
            VALUES (?, ?, 'owner', ?)
        ");

        try {
            $stmt->execute([$this->userId, $device['id'], $device['name']]);

            // Clear the link code
            $stmt = $this->pdo->prepare("
                UPDATE pi_devices
                SET link_code = NULL, link_code_expires = NULL
                WHERE id = ?
            ");
            $stmt->execute([$device['id']]);

            return [
                'ok' => true,
                'message' => 'Device linked successfully',
                'device' => [
                    'id' => $device['id'],
                    'alias' => $device['name']
                ]
            ];
        } catch (PDOException $e) {
            error_log("Device link error: " . $e->getMessage());
            return ['ok' => false, 'error' => 'Failed to link device'];
        }
    }

    /**
     * Unlink a device
     */
    public function unlinkDevice($deviceId) {
        // Check ownership
        $stmt = $this->pdo->prepare("
            SELECT id, role FROM user_devices
            WHERE user_id = ? AND device_id = ?
        ");
        $stmt->execute([$this->userId, $deviceId]);
        $link = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$link) {
            return ['ok' => false, 'error' => 'Device not found'];
        }

        if ($link['role'] !== 'owner') {
            return ['ok' => false, 'error' => 'Only the device owner can unlink it'];
        }

        // Delete link
        $stmt = $this->pdo->prepare("DELETE FROM user_devices WHERE id = ?");
        $stmt->execute([$link['id']]);

        return ['ok' => true, 'message' => 'Device unlinked'];
    }

    /**
     * Update device nickname
     */
    public function updateNickname($deviceId, $nickname) {
        $nickname = trim($nickname);

        if (strlen($nickname) > 100) {
            return ['ok' => false, 'error' => 'Nickname too long'];
        }

        $stmt = $this->pdo->prepare("
            UPDATE user_devices
            SET nickname = ?
            WHERE user_id = ? AND device_id = ?
        ");
        $stmt->execute([$nickname, $this->userId, $deviceId]);

        if ($stmt->rowCount() === 0) {
            return ['ok' => false, 'error' => 'Device not found'];
        }

        return ['ok' => true];
    }

    /**
     * Check if user has access to device
     */
    public function hasAccess($deviceId) {
        $stmt = $this->pdo->prepare("
            SELECT id FROM user_devices
            WHERE user_id = ? AND device_id = ?
        ");
        $stmt->execute([$this->userId, $deviceId]);
        return $stmt->fetch() !== false;
    }

    /**
     * Get latest health data for a device
     */
    public function getDeviceHealth($deviceId) {
        if (!$this->hasAccess($deviceId)) {
            return null;
        }

        $stmt = $this->pdo->prepare("
            SELECT
                ts,
                uptime_seconds,
                disk_used_pct,
                memory_used_pct,
                cpu_temp,
                software_version,
                ip_address,
                controllers_online,
                controllers_offline,
                controllers_json,
                alarms_total,
                alarms_critical,
                alarms_warning,
                issues_json,
                has_issues
            FROM device_health
            WHERE device_id = ?
            ORDER BY ts DESC
            LIMIT 1
        ");
        $stmt->execute([$deviceId]);
        $health = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($health) {
            // Parse JSON fields
            if ($health['controllers_json']) {
                $health['controllers'] = json_decode($health['controllers_json'], true) ?: [];
            } else {
                $health['controllers'] = [];
            }
            if ($health['issues_json']) {
                $health['issues'] = json_decode($health['issues_json'], true) ?: [];
            } else {
                $health['issues'] = [];
            }
            // Calculate uptime display
            if ($health['uptime_seconds']) {
                $days = floor($health['uptime_seconds'] / 86400);
                $hours = floor(($health['uptime_seconds'] % 86400) / 3600);
                $health['uptime_display'] = $days > 0 ? "{$days}d {$hours}h" : "{$hours}h";
            }
        }

        return $health;
    }

    /**
     * Get health history for charts (last 24 hours)
     */
    public function getHealthHistory($deviceId, $hours = 24) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $stmt = $this->pdo->prepare("
            SELECT
                ts,
                cpu_temp,
                memory_used_pct,
                disk_used_pct,
                controllers_online,
                controllers_offline,
                alarms_total
            FROM device_health
            WHERE device_id = ?
              AND ts > DATE_SUB(NOW(), INTERVAL ? HOUR)
            ORDER BY ts ASC
        ");
        $stmt->execute([$deviceId, $hours]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get AI suggestions for a device
     */
    public function getAISuggestions($deviceId, $limit = 5) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $stmt = $this->pdo->prepare("
            SELECT
                id,
                pool,
                suggestion_type,
                title,
                body,
                priority,
                status,
                created_at
            FROM ai_suggestions
            WHERE device_id = ?
              AND status NOT IN ('retracted')
            ORDER BY created_at DESC
            LIMIT ?
        ");
        $stmt->execute([$deviceId, $limit]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get AI question responses for a device
     */
    public function getAIResponses($deviceId, $limit = 10) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $stmt = $this->pdo->prepare("
            SELECT
                r.id,
                r.pool,
                r.answer,
                r.answered_at,
                q.text as question_text,
                q.category
            FROM ai_responses r
            JOIN ai_questions q ON r.question_id = q.id
            WHERE r.device_id = ?
            ORDER BY r.answered_at DESC
            LIMIT ?
        ");
        $stmt->execute([$deviceId, $limit]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Generate a link code for a device (called from Pi)
     * This is a static method called by the device API
     */
    public static function generateLinkCode($deviceId) {
        $pdo = db();

        // Generate 6-character code (A-Z, 0-9, no confusing chars)
        $chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
        $code = '';
        for ($i = 0; $i < 6; $i++) {
            $code .= $chars[random_int(0, strlen($chars) - 1)];
        }

        $expires = date('Y-m-d H:i:s', strtotime('+' . PORTAL_LINK_CODE_MINUTES . ' minutes'));

        $stmt = $pdo->prepare("
            UPDATE pi_devices
            SET link_code = ?, link_code_expires = ?
            WHERE id = ?
        ");
        $stmt->execute([$code, $expires, $deviceId]);

        return [
            'code' => $code,
            'expires_at' => $expires,
            'formatted' => substr($code, 0, 3) . '-' . substr($code, 3, 3)
        ];
    }
}
