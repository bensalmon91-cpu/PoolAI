<?php
/**
 * AI Suggestions API - View and manage AI-generated suggestions
 *
 * GET    /api/ai/suggestions.php              - List suggestions (with filters)
 * GET    /api/ai/suggestions.php?id=X         - Get single suggestion
 * POST   /api/ai/suggestions.php              - Create manual suggestion
 * PUT    /api/ai/suggestions.php?id=X         - Update suggestion (retract, add notes)
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
            if ($id) {
                // Get single suggestion with context
                $stmt = $pdo->prepare("
                    SELECT s.*,
                           d.name as device_name,
                           d.alias as device_alias,
                           d.device_id as device_uuid
                    FROM ai_suggestions s
                    JOIN pi_devices d ON s.device_id = d.id
                    WHERE s.id = ?
                ");
                $stmt->execute([$id]);
                $suggestion = $stmt->fetch(PDO::FETCH_ASSOC);

                if (!$suggestion) {
                    errorResponse('Suggestion not found', 404);
                }

                if ($suggestion['source_data_json']) {
                    $suggestion['source_data'] = json_decode($suggestion['source_data_json'], true);
                }

                // Get other recent suggestions for this device
                $stmt = $pdo->prepare("
                    SELECT id, title, status, created_at, suggestion_type
                    FROM ai_suggestions
                    WHERE device_id = ? AND id != ?
                    ORDER BY created_at DESC
                    LIMIT 10
                ");
                $stmt->execute([$suggestion['device_id'], $id]);
                $suggestion['related_suggestions'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

                successResponse(['suggestion' => $suggestion]);
            } else {
                // List suggestions with filters
                $device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;
                $pool = $_GET['pool'] ?? null;
                $status = $_GET['status'] ?? null;
                $type = $_GET['type'] ?? null;
                $from = $_GET['from'] ?? null;
                $to = $_GET['to'] ?? null;
                $limit = min(intval($_GET['limit'] ?? 100), 500);
                $offset = intval($_GET['offset'] ?? 0);

                $where = [];
                $params = [];

                if ($device_id) {
                    $where[] = 's.device_id = ?';
                    $params[] = $device_id;
                }
                if ($pool) {
                    $where[] = 's.pool = ?';
                    $params[] = $pool;
                }
                if ($status) {
                    $where[] = 's.status = ?';
                    $params[] = $status;
                }
                if ($type) {
                    $where[] = 's.suggestion_type = ?';
                    $params[] = $type;
                }
                if ($from) {
                    $where[] = 's.created_at >= ?';
                    $params[] = $from;
                }
                if ($to) {
                    $where[] = 's.created_at <= ?';
                    $params[] = $to;
                }

                $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

                // Get total count
                $count_stmt = $pdo->prepare("
                    SELECT COUNT(*) FROM ai_suggestions s
                    $where_clause
                ");
                $count_stmt->execute($params);
                $total = $count_stmt->fetchColumn();

                // Get suggestions
                $params[] = $limit;
                $params[] = $offset;
                $stmt = $pdo->prepare("
                    SELECT s.*,
                           d.name as device_name,
                           d.alias as device_alias
                    FROM ai_suggestions s
                    JOIN pi_devices d ON s.device_id = d.id
                    $where_clause
                    ORDER BY s.created_at DESC
                    LIMIT ? OFFSET ?
                ");
                $stmt->execute($params);
                $suggestions = $stmt->fetchAll(PDO::FETCH_ASSOC);

                // Get status counts for dashboard
                $status_counts = $pdo->query("
                    SELECT status, COUNT(*) as count
                    FROM ai_suggestions
                    GROUP BY status
                ")->fetchAll(PDO::FETCH_KEY_PAIR);

                // Get type counts
                $type_counts = $pdo->query("
                    SELECT suggestion_type, COUNT(*) as count
                    FROM ai_suggestions
                    WHERE suggestion_type IS NOT NULL
                    GROUP BY suggestion_type
                ")->fetchAll(PDO::FETCH_KEY_PAIR);

                successResponse([
                    'suggestions' => $suggestions,
                    'total' => $total,
                    'limit' => $limit,
                    'offset' => $offset,
                    'status_counts' => $status_counts,
                    'type_counts' => $type_counts
                ]);
            }
            break;

        case 'POST':
            // Create manual suggestion
            $input = getJsonInput();

            $required = ['device_id', 'title', 'body'];
            if ($error = validateRequired($required, $input)) {
                errorResponse($error);
            }

            // Verify device exists
            $stmt = $pdo->prepare("SELECT id FROM pi_devices WHERE id = ?");
            $stmt->execute([$input['device_id']]);
            if (!$stmt->fetch()) {
                errorResponse('Device not found', 404);
            }

            $stmt = $pdo->prepare("
                INSERT INTO ai_suggestions
                (device_id, pool, suggestion_type, title, body, priority, confidence,
                 source_data_json, status, admin_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            ");
            $stmt->execute([
                $input['device_id'],
                $input['pool'] ?? '',
                $input['suggestion_type'] ?? 'manual',
                $input['title'],
                $input['body'],
                $input['priority'] ?? 3,
                $input['confidence'] ?? 1.0,
                isset($input['source_data']) ? json_encode($input['source_data']) : null,
                $input['admin_notes'] ?? 'Manually created by admin'
            ]);

            $new_id = $pdo->lastInsertId();

            successResponse(['id' => $new_id], 'Suggestion created');
            break;

        case 'PUT':
            // Update suggestion
            if (!$id) {
                errorResponse('Suggestion ID required');
            }

            $input = getJsonInput();

            $stmt = $pdo->prepare("SELECT id, status FROM ai_suggestions WHERE id = ?");
            $stmt->execute([$id]);
            $suggestion = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$suggestion) {
                errorResponse('Suggestion not found', 404);
            }

            $updates = [];
            $params = [];

            // Handle retraction specially
            if (isset($input['retract']) && $input['retract']) {
                $updates[] = 'status = ?';
                $params[] = 'retracted';
                $updates[] = 'retracted_at = NOW()';
                if (isset($input['retracted_reason'])) {
                    $updates[] = 'retracted_reason = ?';
                    $params[] = $input['retracted_reason'];
                }
            } else {
                // Normal field updates
                if (array_key_exists('status', $input)) {
                    $valid_statuses = ['pending', 'delivered', 'read', 'acted_upon', 'dismissed', 'retracted'];
                    if (!in_array($input['status'], $valid_statuses)) {
                        errorResponse('Invalid status');
                    }
                    $updates[] = 'status = ?';
                    $params[] = $input['status'];
                }
                if (array_key_exists('admin_notes', $input)) {
                    $updates[] = 'admin_notes = ?';
                    $params[] = $input['admin_notes'];
                }
                if (array_key_exists('priority', $input)) {
                    $updates[] = 'priority = ?';
                    $params[] = intval($input['priority']);
                }
            }

            if (empty($updates)) {
                errorResponse('No fields to update');
            }

            $params[] = $id;
            $stmt = $pdo->prepare("
                UPDATE ai_suggestions
                SET " . implode(', ', $updates) . "
                WHERE id = ?
            ");
            $stmt->execute($params);

            successResponse([], 'Suggestion updated');
            break;

        default:
            errorResponse('Method not allowed', 405);
    }
} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
