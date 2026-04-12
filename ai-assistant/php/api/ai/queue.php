<?php
/**
 * AI Question Queue API - Manage question queue per device
 *
 * GET    /api/ai/queue.php                     - List queue entries (with filters)
 * POST   /api/ai/queue.php                     - Manually queue question for device
 * DELETE /api/ai/queue.php?id=X                - Remove from queue
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
requireAdmin();

$pdo = db();
$method = $_SERVER['REQUEST_METHOD'];
$id = isset($_GET['id']) ? intval($_GET['id']) : null;

try {
    switch ($method) {
        case 'GET':
            // List queue entries with filters
            $device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;
            $status = $_GET['status'] ?? null;
            $pool = $_GET['pool'] ?? null;
            $limit = min(intval($_GET['limit'] ?? 100), 500);
            $offset = intval($_GET['offset'] ?? 0);

            $where = [];
            $params = [];

            if ($device_id) {
                $where[] = 'qq.device_id = ?';
                $params[] = $device_id;
            }
            if ($status) {
                $where[] = 'qq.status = ?';
                $params[] = $status;
            }
            if ($pool) {
                $where[] = 'qq.pool = ?';
                $params[] = $pool;
            }

            $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

            // Get total count
            $count_stmt = $pdo->prepare("
                SELECT COUNT(*) FROM ai_question_queue qq
                $where_clause
            ");
            $count_stmt->execute($params);
            $total = $count_stmt->fetchColumn();

            // Get queue entries
            $params[] = $limit;
            $params[] = $offset;
            $stmt = $pdo->prepare("
                SELECT qq.*,
                       q.text as question_text,
                       q.type as question_type,
                       q.category,
                       q.priority as question_priority,
                       d.name as device_name,
                       d.alias as device_alias
                FROM ai_question_queue qq
                JOIN ai_questions q ON qq.question_id = q.id
                JOIN pi_devices d ON qq.device_id = d.id
                $where_clause
                ORDER BY qq.created_at DESC
                LIMIT ? OFFSET ?
            ");
            $stmt->execute($params);
            $queue = $stmt->fetchAll(PDO::FETCH_ASSOC);

            // Get status counts
            $status_counts = $pdo->query("
                SELECT status, COUNT(*) as count
                FROM ai_question_queue
                GROUP BY status
            ")->fetchAll(PDO::FETCH_KEY_PAIR);

            successResponse([
                'queue' => $queue,
                'total' => $total,
                'limit' => $limit,
                'offset' => $offset,
                'status_counts' => $status_counts
            ]);
            break;

        case 'POST':
            // Manually queue question for device
            $input = getJsonInput();

            $required = ['device_id', 'question_id'];
            if ($error = validateRequired($required, $input)) {
                errorResponse($error);
            }

            // Verify device exists
            $stmt = $pdo->prepare("SELECT id FROM pi_devices WHERE id = ?");
            $stmt->execute([$input['device_id']]);
            if (!$stmt->fetch()) {
                errorResponse('Device not found', 404);
            }

            // Verify question exists
            $stmt = $pdo->prepare("SELECT id FROM ai_questions WHERE id = ? AND is_active = 1");
            $stmt->execute([$input['question_id']]);
            if (!$stmt->fetch()) {
                errorResponse('Question not found or inactive', 404);
            }

            // Check if already queued and pending
            $stmt = $pdo->prepare("
                SELECT id FROM ai_question_queue
                WHERE device_id = ? AND question_id = ? AND pool = ? AND status = 'pending'
            ");
            $stmt->execute([
                $input['device_id'],
                $input['question_id'],
                $input['pool'] ?? ''
            ]);
            if ($stmt->fetch()) {
                errorResponse('Question already queued for this device/pool');
            }

            // Calculate expiry (default 7 days)
            $expires_days = $input['expires_days'] ?? 7;
            $expires_at = date('Y-m-d H:i:s', strtotime("+{$expires_days} days"));

            $stmt = $pdo->prepare("
                INSERT INTO ai_question_queue
                (device_id, question_id, pool, triggered_by, status, expires_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
            ");
            $stmt->execute([
                $input['device_id'],
                $input['question_id'],
                $input['pool'] ?? '',
                $input['triggered_by'] ?? 'manual_admin',
                $expires_at
            ]);

            $new_id = $pdo->lastInsertId();

            successResponse(['id' => $new_id], 'Question queued');
            break;

        case 'DELETE':
            // Remove from queue
            if (!$id) {
                errorResponse('Queue ID required');
            }

            $stmt = $pdo->prepare("DELETE FROM ai_question_queue WHERE id = ?");
            $stmt->execute([$id]);

            if ($stmt->rowCount() === 0) {
                errorResponse('Queue entry not found', 404);
            }

            successResponse([], 'Queue entry removed');
            break;

        default:
            errorResponse('Method not allowed', 405);
    }
} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
