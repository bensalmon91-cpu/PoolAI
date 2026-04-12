<?php
/**
 * AI Heartbeat Extension
 *
 * This file provides functions to be included in the main heartbeat.php
 * to add AI questions and suggestions to the heartbeat response.
 *
 * Usage in heartbeat.php:
 *   require_once __DIR__ . '/ai/heartbeat_extension.php';
 *   $ai_data = getAIHeartbeatData($pdo, $device_id);
 *   // Include in response: 'ai' => $ai_data
 */

/**
 * Get AI data to include in heartbeat response
 *
 * @param PDO $pdo Database connection
 * @param int $device_id Device ID
 * @return array AI data (questions and suggestions)
 */
function getAIHeartbeatData(PDO $pdo, int $device_id): array {
    $ai_data = [
        'questions' => [],
        'suggestions' => []
    ];

    try {
        // Get pending questions for this device
        $stmt = $pdo->prepare("
            SELECT
                qq.id as queue_id,
                q.id as question_id,
                q.text,
                q.input_type,
                q.options_json,
                qq.pool,
                q.priority
            FROM ai_question_queue qq
            JOIN ai_questions q ON qq.question_id = q.id
            WHERE qq.device_id = ?
                AND qq.status = 'pending'
                AND (qq.expires_at IS NULL OR qq.expires_at > NOW())
            ORDER BY q.priority DESC, qq.created_at ASC
            LIMIT 5
        ");
        $stmt->execute([$device_id]);
        $questions = $stmt->fetchAll(PDO::FETCH_ASSOC);

        foreach ($questions as $q) {
            $ai_data['questions'][] = [
                'queue_id' => (int)$q['queue_id'],
                'question_id' => (int)$q['question_id'],
                'text' => $q['text'],
                'input_type' => $q['input_type'],
                'options' => $q['options_json'] ? json_decode($q['options_json'], true) : [],
                'pool' => $q['pool'] ?? '',
                'priority' => (int)$q['priority']
            ];

            // Mark as delivered
            $update = $pdo->prepare("
                UPDATE ai_question_queue
                SET status = 'delivered', delivered_at = NOW()
                WHERE id = ?
            ");
            $update->execute([$q['queue_id']]);
        }

        // Get pending suggestions for this device
        $stmt = $pdo->prepare("
            SELECT
                id,
                pool,
                suggestion_type as type,
                title,
                body,
                priority
            FROM ai_suggestions
            WHERE device_id = ?
                AND status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 5
        ");
        $stmt->execute([$device_id]);
        $suggestions = $stmt->fetchAll(PDO::FETCH_ASSOC);

        foreach ($suggestions as $s) {
            $ai_data['suggestions'][] = [
                'id' => (int)$s['id'],
                'pool' => $s['pool'] ?? '',
                'type' => $s['type'] ?? 'general',
                'title' => $s['title'],
                'body' => $s['body'],
                'priority' => (int)$s['priority']
            ];

            // Mark as delivered
            $update = $pdo->prepare("
                UPDATE ai_suggestions
                SET status = 'delivered', delivered_at = NOW()
                WHERE id = ?
            ");
            $update->execute([$s['id']]);
        }

    } catch (PDOException $e) {
        // Log error but don't fail the heartbeat
        error_log("AI heartbeat extension error: " . $e->getMessage());
    }

    return $ai_data;
}

/**
 * Process AI responses included in heartbeat
 *
 * @param PDO $pdo Database connection
 * @param int $device_id Device ID
 * @param array $ai_input AI data from heartbeat input
 */
function processAIHeartbeatInput(PDO $pdo, int $device_id, array $ai_input): void {
    try {
        // Process question responses
        if (!empty($ai_input['responses'])) {
            foreach ($ai_input['responses'] as $response) {
                if (empty($response['queue_id']) || empty($response['answer'])) {
                    continue;
                }

                // Verify queue entry belongs to this device
                $stmt = $pdo->prepare("
                    SELECT qq.id, qq.question_id, qq.pool
                    FROM ai_question_queue qq
                    WHERE qq.id = ? AND qq.device_id = ?
                ");
                $stmt->execute([$response['queue_id'], $device_id]);
                $queue = $stmt->fetch(PDO::FETCH_ASSOC);

                if (!$queue) {
                    continue;
                }

                $answered_at = $response['answered_at'] ?? date('Y-m-d H:i:s');

                // Insert response
                $stmt = $pdo->prepare("
                    INSERT INTO ai_responses
                    (device_id, question_id, queue_id, pool, answer, answered_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ");
                $stmt->execute([
                    $device_id,
                    $queue['question_id'],
                    $queue['id'],
                    $queue['pool'],
                    $response['answer'],
                    $answered_at
                ]);

                // Update queue status
                $stmt = $pdo->prepare("
                    UPDATE ai_question_queue
                    SET status = 'answered', answered_at = ?
                    WHERE id = ?
                ");
                $stmt->execute([$answered_at, $queue['id']]);

                // Update pool profile
                $stmt = $pdo->prepare("
                    INSERT INTO ai_pool_profiles (device_id, pool, profile_json, questions_answered, last_question_at)
                    VALUES (?, ?, '{}', 1, ?)
                    ON DUPLICATE KEY UPDATE
                        questions_answered = questions_answered + 1,
                        last_question_at = VALUES(last_question_at)
                ");
                $stmt->execute([$device_id, $queue['pool'], $answered_at]);
            }
        }

        // Process suggestion feedback
        if (!empty($ai_input['suggestion_actions'])) {
            foreach ($ai_input['suggestion_actions'] as $action) {
                if (empty($action['suggestion_id']) || empty($action['action'])) {
                    continue;
                }

                $valid_actions = ['read', 'acted_upon', 'dismissed'];
                if (!in_array($action['action'], $valid_actions)) {
                    continue;
                }

                $updates = ['status = ?'];
                $params = [$action['action']];

                if ($action['action'] === 'read') {
                    $updates[] = 'read_at = NOW()';
                }

                if (!empty($action['feedback'])) {
                    $updates[] = 'user_feedback = ?';
                    $params[] = $action['feedback'];
                }

                $params[] = $action['suggestion_id'];
                $params[] = $device_id;

                $stmt = $pdo->prepare("
                    UPDATE ai_suggestions
                    SET " . implode(', ', $updates) . "
                    WHERE id = ? AND device_id = ?
                ");
                $stmt->execute($params);
            }
        }

    } catch (PDOException $e) {
        error_log("AI heartbeat input processing error: " . $e->getMessage());
    }
}

/*
 * INTEGRATION INSTRUCTIONS
 * ========================
 *
 * Add to heartbeat.php after line ~117 (after device health is logged):
 *
 * // AI Assistant Integration
 * require_once __DIR__ . '/ai/heartbeat_extension.php';
 *
 * // Process incoming AI responses/actions
 * if (!empty($input['ai'])) {
 *     processAIHeartbeatInput($pdo, $device_id, $input['ai']);
 * }
 *
 * // Get AI data for response
 * $ai_data = getAIHeartbeatData($pdo, $device_id);
 *
 * Then modify the jsonResponse to include:
 *
 * jsonResponse([
 *     'ok' => true,
 *     'commands' => $commands,
 *     'alias_sync' => $sync_alias,
 *     'ai' => $ai_data  // ADD THIS
 * ]);
 */
