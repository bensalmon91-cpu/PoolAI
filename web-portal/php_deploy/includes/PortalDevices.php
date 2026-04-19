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
     * Get latest readings for a device
     */
    public function getLatestReadings($deviceId, $pool = null) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $sql = "
            SELECT pool, metric, value, unit, ts
            FROM device_readings_latest
            WHERE device_id = ?
        ";
        $params = [$deviceId];

        if ($pool !== null) {
            $sql .= " AND pool = ?";
            $params[] = $pool;
        }

        $sql .= " ORDER BY pool, metric";

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

        // Group by pool
        $grouped = [];
        foreach ($rows as $row) {
            $poolName = $row['pool'] ?: 'Default';
            if (!isset($grouped[$poolName])) {
                $grouped[$poolName] = [];
            }
            $grouped[$poolName][$row['metric']] = [
                'value' => $row['value'],
                'unit' => $row['unit'],
                'ts' => $row['ts'],
                'status' => $this->getReadingStatus($row['metric'], $row['value']),
            ];
        }

        return $grouped;
    }

    /**
     * Get reading status (green/yellow/red) based on thresholds
     */
    private function getReadingStatus($metric, $value) {
        $metric = strtolower($metric);
        $value = floatval($value);

        // pH thresholds
        if (strpos($metric, 'ph') !== false) {
            if ($value >= 7.2 && $value <= 7.6) return 'green';
            if ($value >= 7.0 && $value <= 7.8) return 'yellow';
            return 'red';
        }

        // Chlorine thresholds (mg/L)
        if (strpos($metric, 'chlorine') !== false || strpos($metric, 'cl') !== false) {
            if ($value >= 1.0 && $value <= 3.0) return 'green';
            if ($value >= 0.5 && $value <= 4.0) return 'yellow';
            return 'red';
        }

        // ORP thresholds (mV)
        if (strpos($metric, 'orp') !== false) {
            if ($value >= 650 && $value <= 750) return 'green';
            if ($value >= 600 && $value <= 800) return 'yellow';
            return 'red';
        }

        // Temperature - always show as OK unless extreme
        if (strpos($metric, 'temp') !== false) {
            if ($value >= 20 && $value <= 32) return 'green';
            if ($value >= 15 && $value <= 38) return 'yellow';
            return 'red';
        }

        return 'green';  // Default to green for unknown metrics
    }

    /**
     * Get readings history for charts
     */
    public function getReadingsHistory($deviceId, $metric = null, $pool = null, $hours = 24) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $sql = "
            SELECT pool, metric, value, unit, ts
            FROM device_readings_history
            WHERE device_id = ?
              AND ts > DATE_SUB(NOW(), INTERVAL ? HOUR)
        ";
        $params = [$deviceId, $hours];

        if ($metric !== null) {
            $sql .= " AND metric = ?";
            $params[] = $metric;
        }

        if ($pool !== null) {
            $sql .= " AND pool = ?";
            $params[] = $pool;
        }

        $sql .= " ORDER BY ts ASC";

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get current alarms for a device
     */
    public function getCurrentAlarms($deviceId) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $stmt = $this->pdo->prepare("
            SELECT pool, alarm_source, alarm_name, severity, started_at,
                   acknowledged, acknowledged_by, acknowledged_at
            FROM device_alarms_current
            WHERE device_id = ?
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'warning' THEN 2
                    ELSE 3
                END,
                started_at DESC
        ");
        $stmt->execute([$deviceId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get controller status for a device
     */
    public function getControllerStatus($deviceId) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $stmt = $this->pdo->prepare("
            SELECT host, name, is_online, minutes_ago, received_at
            FROM device_controllers_status
            WHERE device_id = ?
            ORDER BY name
        ");
        $stmt->execute([$deviceId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get available pools for a device
     */
    public function getDevicePools($deviceId) {
        if (!$this->hasAccess($deviceId)) {
            return [];
        }

        $stmt = $this->pdo->prepare("
            SELECT DISTINCT pool
            FROM device_readings_latest
            WHERE device_id = ?
            ORDER BY pool
        ");
        $stmt->execute([$deviceId]);
        $rows = $stmt->fetchAll(PDO::FETCH_COLUMN);

        return array_filter($rows, fn($p) => $p !== '');
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
