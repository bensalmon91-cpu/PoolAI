<?php
/**
 * PoolAIssistant Admin - Device Management Service
 *
 * Provides methods for admin device management including:
 * - Getting device details with health data
 * - Getting linked clients
 * - Managing command queue
 * - Viewing health history
 */

require_once __DIR__ . '/../config/database.php';

class AdminDevices {
    private $pdo;

    public function __construct() {
        $this->pdo = db();
    }

    /**
     * Get device with latest health data
     */
    public function getDevice($deviceId) {
        $stmt = $this->pdo->prepare("
            SELECT
                d.id,
                d.device_uuid,
                d.name,
                d.api_key,
                d.is_active,
                d.last_seen,
                d.link_code,
                d.link_code_expires,
                d.created_at,
                h.id as health_id,
                h.ts as health_ts,
                h.uptime_seconds,
                h.disk_used_pct,
                h.memory_used_pct,
                h.cpu_temp,
                h.software_version,
                h.ip_address,
                h.controllers_online,
                h.controllers_offline,
                h.controllers_json,
                h.alarms_total,
                h.alarms_critical,
                h.alarms_warning,
                h.issues_json,
                h.has_issues
            FROM pi_devices d
            LEFT JOIN (
                SELECT h1.*
                FROM device_health h1
                INNER JOIN (
                    SELECT device_id, MAX(ts) as max_ts
                    FROM device_health
                    GROUP BY device_id
                ) h2 ON h1.device_id = h2.device_id AND h1.ts = h2.max_ts
            ) h ON d.id = h.device_id
            WHERE d.id = ?
        ");
        $stmt->execute([$deviceId]);
        $device = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($device) {
            // Calculate online status
            $lastSeen = $device['last_seen'] ? strtotime($device['last_seen']) : null;
            $minutesAgo = $lastSeen ? round((time() - $lastSeen) / 60) : null;
            $device['is_online'] = $minutesAgo !== null && $minutesAgo < 20;
            $device['minutes_ago'] = $minutesAgo;

            // Calculate status badge
            if (!$device['is_online']) {
                $device['status'] = 'offline';
            } elseif ($device['has_issues']) {
                $device['status'] = 'issues';
            } else {
                $device['status'] = 'online';
            }

            // Parse JSON fields
            if ($device['controllers_json']) {
                $device['controllers'] = json_decode($device['controllers_json'], true) ?: [];
            } else {
                $device['controllers'] = [];
            }
            if ($device['issues_json']) {
                $device['issues'] = json_decode($device['issues_json'], true) ?: [];
            } else {
                $device['issues'] = [];
            }

            // Calculate uptime display
            if ($device['uptime_seconds']) {
                $days = floor($device['uptime_seconds'] / 86400);
                $hours = floor(($device['uptime_seconds'] % 86400) / 3600);
                $mins = floor(($device['uptime_seconds'] % 3600) / 60);
                if ($days > 0) {
                    $device['uptime_display'] = "{$days}d {$hours}h";
                } elseif ($hours > 0) {
                    $device['uptime_display'] = "{$hours}h {$mins}m";
                } else {
                    $device['uptime_display'] = "{$mins}m";
                }
            } else {
                $device['uptime_display'] = '-';
            }

            // Mask API key for display
            if ($device['api_key']) {
                $device['api_key_masked'] = substr($device['api_key'], 0, 8) . '...' . substr($device['api_key'], -4);
            }
        }

        return $device;
    }

    /**
     * Get portal users linked to a device
     */
    public function getDeviceClients($deviceId) {
        $stmt = $this->pdo->prepare("
            SELECT
                u.id,
                u.email,
                u.name,
                u.company,
                u.status as user_status,
                ud.role,
                ud.nickname,
                ud.linked_at
            FROM user_devices ud
            JOIN portal_users u ON ud.user_id = u.id
            WHERE ud.device_id = ?
            ORDER BY ud.linked_at ASC
        ");
        $stmt->execute([$deviceId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Get command history for a device
     */
    public function getCommandHistory($deviceId, $limit = 20) {
        $stmt = $this->pdo->prepare("
            SELECT
                id,
                command_type,
                payload,
                status,
                created_at,
                acknowledged_at,
                completed_at,
                result
            FROM device_commands
            WHERE device_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ");
        $stmt->execute([$deviceId, $limit]);
        $commands = $stmt->fetchAll(PDO::FETCH_ASSOC);

        // Parse payload JSON
        foreach ($commands as &$cmd) {
            if ($cmd['payload']) {
                $cmd['payload_data'] = json_decode($cmd['payload'], true) ?: [];
            } else {
                $cmd['payload_data'] = [];
            }
            if ($cmd['result']) {
                $cmd['result_data'] = json_decode($cmd['result'], true) ?: [];
            } else {
                $cmd['result_data'] = [];
            }
        }

        return $commands;
    }

    /**
     * Get health history for a device
     */
    public function getHealthHistory($deviceId, $limit = 10) {
        $stmt = $this->pdo->prepare("
            SELECT
                id,
                ts,
                uptime_seconds,
                disk_used_pct,
                memory_used_pct,
                cpu_temp,
                software_version,
                ip_address,
                controllers_online,
                controllers_offline,
                alarms_total,
                alarms_critical,
                has_issues
            FROM device_health
            WHERE device_id = ?
            ORDER BY ts DESC
            LIMIT ?
        ");
        $stmt->execute([$deviceId, $limit]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /**
     * Create a command for a device
     */
    public function createCommand($deviceId, $type, $payload = [], $adminUsername = null) {
        // Validate command type. Keep in sync with device_commands.command_type ENUM.
        $validTypes = ['upload', 'restart', 'update', 'apply_settings'];
        if (!in_array($type, $validTypes)) {
            return ['ok' => false, 'error' => 'Invalid command type'];
        }

        // Check for existing pending command of same type
        $stmt = $this->pdo->prepare("
            SELECT id FROM device_commands
            WHERE device_id = ? AND command_type = ? AND status IN ('pending', 'acknowledged')
        ");
        $stmt->execute([$deviceId, $type]);
        if ($stmt->fetch()) {
            return ['ok' => false, 'error' => 'A ' . $type . ' command is already pending'];
        }

        // Add metadata to payload
        $payload['requested_by'] = $adminUsername ?: 'admin';
        $payload['requested_at'] = date('Y-m-d H:i:s');

        // Create command
        $stmt = $this->pdo->prepare("
            INSERT INTO device_commands (device_id, command_type, payload, status, created_at)
            VALUES (?, ?, ?, 'pending', NOW())
        ");
        $stmt->execute([$deviceId, $type, json_encode($payload)]);

        return [
            'ok' => true,
            'command_id' => $this->pdo->lastInsertId(),
            'message' => ucfirst($type) . ' command queued. Device will execute on next heartbeat.'
        ];
    }

    /**
     * Clear issues flag for a device
     */
    public function clearIssues($deviceId) {
        $stmt = $this->pdo->prepare("
            UPDATE device_health
            SET has_issues = 0, issues_json = NULL
            WHERE device_id = ?
            ORDER BY ts DESC
            LIMIT 1
        ");
        $stmt->execute([$deviceId]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Get controller status for a device
     */
    public function getControllerStatus($deviceId) {
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
     * Get current alarms for a device
     */
    public function getCurrentAlarms($deviceId) {
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
     * Get latest readings for a device
     */
    public function getLatestReadings($deviceId) {
        $stmt = $this->pdo->prepare("
            SELECT pool, metric, value, unit, ts
            FROM device_readings_latest
            WHERE device_id = ?
            ORDER BY pool, metric
        ");
        $stmt->execute([$deviceId]);
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
            ];
        }

        return $grouped;
    }
}
