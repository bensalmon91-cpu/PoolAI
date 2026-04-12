<?php
/**
 * PoolAIssistant Mobile Device Management
 */

require_once __DIR__ . '/../config/database.php';

class MobileDevices {
    private $pdo;
    private $userId;

    public function __construct($userId) {
        $this->pdo = db();
        $this->userId = (int)$userId;
    }

    public function getDevices() {
        $stmt = $this->pdo->prepare('
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
                h.controllers_online,
                h.controllers_offline,
                h.alarms_total,
                h.alarms_critical,
                h.has_issues,
                CASE
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 20 MINUTE) THEN \'online\'
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN \'away\'
                    ELSE \'offline\'
                END as status
            FROM user_devices ud
            JOIN pi_devices d ON ud.device_id = d.id
            LEFT JOIN (
                SELECT device_id, ip_address, software_version, controllers_online,
                       controllers_offline, alarms_total, alarms_critical, has_issues
                FROM device_health h1
                WHERE ts = (SELECT MAX(ts) FROM device_health h2 WHERE h2.device_id = h1.device_id)
            ) h ON h.device_id = d.id
            WHERE ud.user_id = ?
            ORDER BY ud.linked_at DESC
        ');
        $stmt->execute(array($this->userId));
        $devices = $stmt->fetchAll(PDO::FETCH_ASSOC);

        foreach ($devices as &$device) {
            $stmt2 = $this->pdo->prepare('
                SELECT COUNT(*) as count FROM ai_suggestions
                WHERE device_id = ? AND status IN (\'pending\', \'delivered\')
            ');
            $stmt2->execute(array($device['device_id']));
            $row = $stmt2->fetch(PDO::FETCH_ASSOC);
            $device['pending_suggestions'] = (int)$row['count'];
        }

        return $devices;
    }

    public function getDevice($deviceId) {
        $deviceId = (int)$deviceId;
        $stmt = $this->pdo->prepare('
            SELECT
                ud.id as link_id,
                ud.nickname,
                ud.role,
                ud.linked_at,
                d.id as device_id,
                d.device_uuid,
                d.name as alias,
                d.last_seen,
                CASE
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 20 MINUTE) THEN \'online\'
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN \'away\'
                    ELSE \'offline\'
                END as status
            FROM user_devices ud
            JOIN pi_devices d ON ud.device_id = d.id
            WHERE ud.user_id = ? AND d.id = ?
        ');
        $stmt->execute(array($this->userId, $deviceId));
        $device = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$device) {
            return null;
        }

        $device['health'] = $this->getDeviceHealth($deviceId);
        $device['suggestions'] = $this->getAISuggestions($deviceId, 5);
        $device['pending_questions'] = $this->getPendingQuestions($deviceId);

        return $device;
    }

    public function hasAccess($deviceId) {
        $stmt = $this->pdo->prepare('SELECT id FROM user_devices WHERE user_id = ? AND device_id = ?');
        $stmt->execute(array($this->userId, (int)$deviceId));
        return $stmt->fetch() !== false;
    }

    public function getDeviceHealth($deviceId) {
        if (!$this->hasAccess($deviceId)) {
            return null;
        }

        $stmt = $this->pdo->prepare('
            SELECT
                ts, uptime_seconds, disk_used_pct, memory_used_pct, cpu_temp,
                software_version, ip_address, controllers_online, controllers_offline,
                controllers_json, alarms_total, alarms_critical, alarms_warning,
                issues_json, has_issues
            FROM device_health
            WHERE device_id = ?
            ORDER BY ts DESC
            LIMIT 1
        ');
        $stmt->execute(array((int)$deviceId));
        $health = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$health) {
            return null;
        }

        $health['controllers'] = array();
        if (!empty($health['controllers_json'])) {
            $decoded = json_decode($health['controllers_json'], true);
            if (is_array($decoded)) {
                $health['controllers'] = $decoded;
            }
        }

        $health['issues'] = array();
        if (!empty($health['issues_json'])) {
            $decoded = json_decode($health['issues_json'], true);
            if (is_array($decoded)) {
                $health['issues'] = $decoded;
            }
        }

        unset($health['controllers_json']);
        unset($health['issues_json']);

        if ($health['uptime_seconds']) {
            $days = floor($health['uptime_seconds'] / 86400);
            $hours = floor(($health['uptime_seconds'] % 86400) / 3600);
            if ($days > 0) {
                $health['uptime_display'] = $days . 'd ' . $hours . 'h';
            } else {
                $health['uptime_display'] = $hours . 'h';
            }
        }

        return $health;
    }

    public function getHealthHistory($deviceId, $hours = 24) {
        if (!$this->hasAccess($deviceId)) {
            return array();
        }

        $stmt = $this->pdo->prepare('
            SELECT ts, cpu_temp, memory_used_pct, disk_used_pct,
                   controllers_online, controllers_offline, alarms_total
            FROM device_health
            WHERE device_id = ? AND ts > DATE_SUB(NOW(), INTERVAL ? HOUR)
            ORDER BY ts ASC
        ');
        $stmt->execute(array((int)$deviceId, (int)$hours));
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    public function linkDevice($linkCode) {
        $linkCode = strtoupper(trim($linkCode));
        $linkCode = preg_replace('/[^A-Z0-9]/', '', $linkCode);

        if (strlen($linkCode) !== 6) {
            return array('ok' => false, 'error' => 'Invalid link code format');
        }

        $stmt = $this->pdo->prepare('
            SELECT id, name, device_uuid FROM pi_devices
            WHERE link_code = ? AND link_code_expires > NOW()
        ');
        $stmt->execute(array($linkCode));
        $device = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$device) {
            return array('ok' => false, 'error' => 'Invalid or expired link code');
        }

        $stmt = $this->pdo->prepare('SELECT id FROM user_devices WHERE user_id = ? AND device_id = ?');
        $stmt->execute(array($this->userId, $device['id']));
        if ($stmt->fetch()) {
            return array('ok' => false, 'error' => 'This device is already linked to your account');
        }

        try {
            $stmt = $this->pdo->prepare('INSERT INTO user_devices (user_id, device_id, role, nickname) VALUES (?, ?, \'owner\', ?)');
            $stmt->execute(array($this->userId, $device['id'], $device['name']));

            $stmt = $this->pdo->prepare('UPDATE pi_devices SET link_code = NULL, link_code_expires = NULL WHERE id = ?');
            $stmt->execute(array($device['id']));

            $stmt = $this->pdo->prepare('INSERT IGNORE INTO user_notification_prefs (user_id, device_id) VALUES (?, ?)');
            $stmt->execute(array($this->userId, $device['id']));

            return array(
                'ok' => true,
                'message' => 'Device linked successfully',
                'device' => array(
                    'id' => $device['id'],
                    'alias' => $device['name'],
                    'device_uuid' => $device['device_uuid']
                )
            );
        } catch (PDOException $e) {
            error_log('Device link error: ' . $e->getMessage());
            return array('ok' => false, 'error' => 'Failed to link device');
        }
    }

    public function unlinkDevice($deviceId) {
        $stmt = $this->pdo->prepare('SELECT id, role FROM user_devices WHERE user_id = ? AND device_id = ?');
        $stmt->execute(array($this->userId, (int)$deviceId));
        $link = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$link) {
            return array('ok' => false, 'error' => 'Device not found');
        }

        if ($link['role'] !== 'owner') {
            return array('ok' => false, 'error' => 'Only the device owner can unlink it');
        }

        $stmt = $this->pdo->prepare('DELETE FROM user_devices WHERE id = ?');
        $stmt->execute(array($link['id']));

        return array('ok' => true, 'message' => 'Device unlinked');
    }

    public function updateNickname($deviceId, $nickname) {
        $nickname = trim($nickname);

        if (strlen($nickname) > 100) {
            return array('ok' => false, 'error' => 'Nickname too long (max 100 characters)');
        }

        $stmt = $this->pdo->prepare('UPDATE user_devices SET nickname = ? WHERE user_id = ? AND device_id = ?');
        $stmt->execute(array($nickname, $this->userId, (int)$deviceId));

        if ($stmt->rowCount() === 0) {
            return array('ok' => false, 'error' => 'Device not found');
        }

        return array('ok' => true);
    }

    public function getAISuggestions($deviceId, $limit = 10, $status = null) {
        if (!$this->hasAccess($deviceId)) {
            return array();
        }

        $sql = 'SELECT id, pool, suggestion_type, title, body, priority, confidence, status, created_at, delivered_at, read_at FROM ai_suggestions WHERE device_id = ? AND status != \'retracted\'';
        $params = array((int)$deviceId);

        if ($status !== null) {
            $sql .= ' AND status = ?';
            $params[] = $status;
        }

        $sql .= ' ORDER BY created_at DESC LIMIT ' . (int)$limit;

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    public function getPendingQuestions($deviceId) {
        if (!$this->hasAccess($deviceId)) {
            return array();
        }

        $stmt = $this->pdo->prepare('
            SELECT
                qq.id as queue_id, qq.question_id, qq.pool, qq.triggered_by, qq.created_at,
                q.text, q.input_type, q.options_json, q.priority, q.category
            FROM ai_question_queue qq
            JOIN ai_questions q ON qq.question_id = q.id
            WHERE qq.device_id = ?
              AND qq.status IN (\'pending\', \'delivered\')
              AND (qq.expires_at IS NULL OR qq.expires_at > NOW())
            ORDER BY q.priority ASC, qq.created_at ASC
            LIMIT 5
        ');
        $stmt->execute(array((int)$deviceId));
        $questions = $stmt->fetchAll(PDO::FETCH_ASSOC);

        foreach ($questions as &$q) {
            $q['options'] = array();
            if (!empty($q['options_json'])) {
                $decoded = json_decode($q['options_json'], true);
                if (is_array($decoded)) {
                    $q['options'] = $decoded;
                }
            }
            unset($q['options_json']);
        }

        return $questions;
    }

    public function answerQuestion($deviceId, $queueId, $answer, $answerJson = null) {
        if (!$this->hasAccess($deviceId)) {
            return array('ok' => false, 'error' => 'Access denied');
        }

        $stmt = $this->pdo->prepare('SELECT id, question_id, pool, status FROM ai_question_queue WHERE id = ? AND device_id = ?');
        $stmt->execute(array((int)$queueId, (int)$deviceId));
        $queue = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$queue) {
            return array('ok' => false, 'error' => 'Question not found');
        }

        if ($queue['status'] === 'answered') {
            return array('ok' => false, 'error' => 'Question already answered');
        }

        try {
            $this->pdo->beginTransaction();

            $answerJsonStr = null;
            if ($answerJson !== null && is_array($answerJson)) {
                $answerJsonStr = json_encode($answerJson);
            }

            $stmt = $this->pdo->prepare('INSERT INTO ai_responses (device_id, question_id, queue_id, pool, answer, answer_json, answered_at) VALUES (?, ?, ?, ?, ?, ?, NOW())');
            $stmt->execute(array(
                (int)$deviceId,
                $queue['question_id'],
                (int)$queueId,
                $queue['pool'],
                $answer,
                $answerJsonStr
            ));

            $stmt = $this->pdo->prepare('UPDATE ai_question_queue SET status = \'answered\', answered_at = NOW() WHERE id = ?');
            $stmt->execute(array((int)$queueId));

            $stmt = $this->pdo->prepare('INSERT INTO ai_pool_profiles (device_id, pool, profile_json, questions_answered, last_question_at) VALUES (?, ?, \'{}\', 1, NOW()) ON DUPLICATE KEY UPDATE questions_answered = questions_answered + 1, last_question_at = NOW()');
            $stmt->execute(array((int)$deviceId, $queue['pool']));

            $this->pdo->commit();
            return array('ok' => true, 'message' => 'Answer submitted');
        } catch (PDOException $e) {
            $this->pdo->rollBack();
            error_log('Answer submission error: ' . $e->getMessage());
            return array('ok' => false, 'error' => 'Failed to submit answer');
        }
    }

    public function suggestionFeedback($deviceId, $suggestionId, $action, $feedback = null) {
        if (!$this->hasAccess($deviceId)) {
            return array('ok' => false, 'error' => 'Access denied');
        }

        $validActions = array('read', 'acted_upon', 'dismissed');
        if (!in_array($action, $validActions)) {
            return array('ok' => false, 'error' => 'Invalid action');
        }

        $stmt = $this->pdo->prepare('SELECT id, status FROM ai_suggestions WHERE id = ? AND device_id = ?');
        $stmt->execute(array((int)$suggestionId, (int)$deviceId));
        $suggestion = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$suggestion) {
            return array('ok' => false, 'error' => 'Suggestion not found');
        }

        $sql = 'UPDATE ai_suggestions SET status = ?';
        $params = array($action);

        if ($action === 'read' && $suggestion['status'] === 'delivered') {
            $sql .= ', read_at = NOW()';
        }

        if ($feedback !== null) {
            $sql .= ', user_feedback = ?';
            $params[] = $feedback;
        }

        $sql .= ' WHERE id = ?';
        $params[] = (int)$suggestionId;

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);

        return array('ok' => true);
    }

    public function getNotificationPrefs($deviceId = null) {
        $stmt = $this->pdo->prepare('SELECT * FROM user_notification_prefs WHERE user_id = ? AND (device_id IS NULL OR device_id = ?)');
        $stmt->execute(array($this->userId, $deviceId));
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    public function updateNotificationPrefs($prefs, $deviceId = null) {
        $allowedFields = array(
            'notify_alarms', 'notify_suggestions', 'notify_device_offline',
            'notify_maintenance_due', 'quiet_hours_start', 'quiet_hours_end'
        );

        $updates = array();
        $updateParams = array();
        $fields = array();
        $values = array();

        foreach ($allowedFields as $field) {
            if (isset($prefs[$field])) {
                $fields[] = $field;
                $values[] = $prefs[$field];
                $updates[] = $field . ' = ?';
                $updateParams[] = $prefs[$field];
            }
        }

        if (empty($updates)) {
            return array('ok' => false, 'error' => 'No valid preferences to update');
        }

        $placeholders = array_fill(0, count($fields), '?');
        $sql = 'INSERT INTO user_notification_prefs (user_id, device_id, ' . implode(', ', $fields) . ') ';
        $sql .= 'VALUES (?, ?, ' . implode(', ', $placeholders) . ') ';
        $sql .= 'ON DUPLICATE KEY UPDATE ' . implode(', ', $updates);

        $params = array_merge(array($this->userId, $deviceId), $values, $updateParams);

        try {
            $stmt = $this->pdo->prepare($sql);
            $stmt->execute($params);
            return array('ok' => true);
        } catch (PDOException $e) {
            error_log('Notification prefs update error: ' . $e->getMessage());
            return array('ok' => false, 'error' => 'Failed to update preferences');
        }
    }
}
