<?php
/**
 * AI Responses API - View and manage user responses
 *
 * GET    /api/ai/responses.php              - List responses (with filters)
 * GET    /api/ai/responses.php?id=X         - Get single response with context
 * PUT    /api/ai/responses.php?id=X         - Update response (flag, add notes)
 * GET    /api/ai/responses.php?export=csv   - Export responses as CSV
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
            // Check for export
            if (isset($_GET['export']) && $_GET['export'] === 'csv') {
                exportResponsesCsv($pdo);
                exit;
            }

            if ($id) {
                // Get single response with full context
                $stmt = $pdo->prepare("
                    SELECT r.*,
                           q.text as question_text,
                           q.type as question_type,
                           q.category as question_category,
                           q.input_type,
                           q.options_json,
                           d.name as device_name,
                           d.alias as device_alias,
                           d.device_id as device_uuid
                    FROM ai_responses r
                    JOIN ai_questions q ON r.question_id = q.id
                    JOIN pi_devices d ON r.device_id = d.id
                    WHERE r.id = ?
                ");
                $stmt->execute([$id]);
                $response = $stmt->fetch(PDO::FETCH_ASSOC);

                if (!$response) {
                    errorResponse('Response not found', 404);
                }

                if ($response['options_json']) {
                    $response['options'] = json_decode($response['options_json'], true);
                }

                // Get other responses from same device/pool for context
                $stmt = $pdo->prepare("
                    SELECT r.id, r.answer, r.answered_at, q.text as question_text
                    FROM ai_responses r
                    JOIN ai_questions q ON r.question_id = q.id
                    WHERE r.device_id = ? AND r.pool = ? AND r.id != ?
                    ORDER BY r.answered_at DESC
                    LIMIT 10
                ");
                $stmt->execute([$response['device_id'], $response['pool'], $id]);
                $response['related_responses'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

                successResponse(['response' => $response]);
            } else {
                // List responses with filters
                $device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;
                $pool = $_GET['pool'] ?? null;
                $question_id = isset($_GET['question_id']) ? intval($_GET['question_id']) : null;
                $flagged = isset($_GET['flagged']) ? ($_GET['flagged'] === '1') : null;
                $from = $_GET['from'] ?? null;
                $to = $_GET['to'] ?? null;
                $category = $_GET['category'] ?? null;
                $limit = min(intval($_GET['limit'] ?? 100), 500);
                $offset = intval($_GET['offset'] ?? 0);

                $where = [];
                $params = [];

                if ($device_id) {
                    $where[] = 'r.device_id = ?';
                    $params[] = $device_id;
                }
                if ($pool) {
                    $where[] = 'r.pool = ?';
                    $params[] = $pool;
                }
                if ($question_id) {
                    $where[] = 'r.question_id = ?';
                    $params[] = $question_id;
                }
                if ($flagged !== null) {
                    $where[] = 'r.flagged = ?';
                    $params[] = $flagged ? 1 : 0;
                }
                if ($from) {
                    $where[] = 'r.answered_at >= ?';
                    $params[] = $from;
                }
                if ($to) {
                    $where[] = 'r.answered_at <= ?';
                    $params[] = $to;
                }
                if ($category) {
                    $where[] = 'q.category = ?';
                    $params[] = $category;
                }

                $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

                // Get total count
                $count_stmt = $pdo->prepare("
                    SELECT COUNT(*) FROM ai_responses r
                    JOIN ai_questions q ON r.question_id = q.id
                    $where_clause
                ");
                $count_stmt->execute($params);
                $total = $count_stmt->fetchColumn();

                // Get responses
                $params[] = $limit;
                $params[] = $offset;
                $stmt = $pdo->prepare("
                    SELECT r.*,
                           q.text as question_text,
                           q.type as question_type,
                           q.category as question_category,
                           d.name as device_name,
                           d.alias as device_alias
                    FROM ai_responses r
                    JOIN ai_questions q ON r.question_id = q.id
                    JOIN pi_devices d ON r.device_id = d.id
                    $where_clause
                    ORDER BY r.answered_at DESC
                    LIMIT ? OFFSET ?
                ");
                $stmt->execute($params);
                $responses = $stmt->fetchAll(PDO::FETCH_ASSOC);

                // Get filter options
                $devices = $pdo->query("
                    SELECT DISTINCT d.id, COALESCE(d.alias, d.name) as name
                    FROM ai_responses r
                    JOIN pi_devices d ON r.device_id = d.id
                    ORDER BY name
                ")->fetchAll(PDO::FETCH_ASSOC);

                $categories = $pdo->query("
                    SELECT DISTINCT q.category
                    FROM ai_responses r
                    JOIN ai_questions q ON r.question_id = q.id
                    WHERE q.category IS NOT NULL
                    ORDER BY q.category
                ")->fetchAll(PDO::FETCH_COLUMN);

                successResponse([
                    'responses' => $responses,
                    'total' => $total,
                    'limit' => $limit,
                    'offset' => $offset,
                    'filters' => [
                        'devices' => $devices,
                        'categories' => $categories
                    ]
                ]);
            }
            break;

        case 'PUT':
            // Update response (flag, add notes)
            if (!$id) {
                errorResponse('Response ID required');
            }

            $input = getJsonInput();

            $stmt = $pdo->prepare("SELECT id FROM ai_responses WHERE id = ?");
            $stmt->execute([$id]);
            if (!$stmt->fetch()) {
                errorResponse('Response not found', 404);
            }

            $updates = [];
            $params = [];

            if (array_key_exists('flagged', $input)) {
                $updates[] = 'flagged = ?';
                $params[] = $input['flagged'] ? 1 : 0;
            }
            if (array_key_exists('admin_notes', $input)) {
                $updates[] = 'admin_notes = ?';
                $params[] = $input['admin_notes'];
            }

            if (empty($updates)) {
                errorResponse('No fields to update');
            }

            $params[] = $id;
            $stmt = $pdo->prepare("
                UPDATE ai_responses
                SET " . implode(', ', $updates) . "
                WHERE id = ?
            ");
            $stmt->execute($params);

            successResponse([], 'Response updated');
            break;

        default:
            errorResponse('Method not allowed', 405);
    }
} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}

/**
 * Export responses as CSV
 */
function exportResponsesCsv(PDO $pdo): void {
    $device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;
    $from = $_GET['from'] ?? date('Y-m-d', strtotime('-30 days'));
    $to = $_GET['to'] ?? date('Y-m-d');

    $where = ['r.answered_at >= ?', 'r.answered_at <= ?'];
    $params = [$from, $to . ' 23:59:59'];

    if ($device_id) {
        $where[] = 'r.device_id = ?';
        $params[] = $device_id;
    }

    $where_clause = 'WHERE ' . implode(' AND ', $where);

    $stmt = $pdo->prepare("
        SELECT
            COALESCE(d.alias, d.name) as device,
            r.pool,
            q.text as question,
            q.category,
            r.answer,
            r.answered_at,
            r.flagged,
            r.admin_notes
        FROM ai_responses r
        JOIN ai_questions q ON r.question_id = q.id
        JOIN pi_devices d ON r.device_id = d.id
        $where_clause
        ORDER BY r.answered_at DESC
    ");
    $stmt->execute($params);

    header('Content-Type: text/csv');
    header('Content-Disposition: attachment; filename="responses_' . date('Y-m-d') . '.csv"');

    $output = fopen('php://output', 'w');
    fputcsv($output, ['Device', 'Pool', 'Question', 'Category', 'Answer', 'Answered At', 'Flagged', 'Admin Notes']);

    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        fputcsv($output, $row);
    }

    fclose($output);
}
