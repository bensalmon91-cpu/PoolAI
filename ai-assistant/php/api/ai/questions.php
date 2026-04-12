<?php
/**
 * AI Questions API - CRUD for question library
 *
 * GET    /api/ai/questions.php           - List all questions
 * GET    /api/ai/questions.php?id=X      - Get single question
 * POST   /api/ai/questions.php           - Create question
 * PUT    /api/ai/questions.php?id=X      - Update question
 * DELETE /api/ai/questions.php?id=X      - Delete question (soft delete)
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
                // Get single question
                $stmt = $pdo->prepare("
                    SELECT q.*,
                           p.text as parent_text
                    FROM ai_questions q
                    LEFT JOIN ai_questions p ON q.follow_up_to = p.id
                    WHERE q.id = ?
                ");
                $stmt->execute([$id]);
                $question = $stmt->fetch(PDO::FETCH_ASSOC);

                if (!$question) {
                    errorResponse('Question not found', 404);
                }

                // Decode JSON options
                if ($question['options_json']) {
                    $question['options'] = json_decode($question['options_json'], true);
                }

                successResponse(['question' => $question]);
            } else {
                // List all questions
                $type = $_GET['type'] ?? null;
                $category = $_GET['category'] ?? null;
                $active_only = !isset($_GET['include_inactive']);

                $where = [];
                $params = [];

                if ($active_only) {
                    $where[] = 'q.is_active = 1';
                }
                if ($type) {
                    $where[] = 'q.type = ?';
                    $params[] = $type;
                }
                if ($category) {
                    $where[] = 'q.category = ?';
                    $params[] = $category;
                }

                $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

                $stmt = $pdo->prepare("
                    SELECT q.*,
                           p.text as parent_text,
                           (SELECT COUNT(*) FROM ai_responses r WHERE r.question_id = q.id) as response_count,
                           (SELECT COUNT(*) FROM ai_question_queue qq WHERE qq.question_id = q.id AND qq.status = 'pending') as pending_count
                    FROM ai_questions q
                    LEFT JOIN ai_questions p ON q.follow_up_to = p.id
                    $where_clause
                    ORDER BY q.type, q.priority DESC, q.id
                ");
                $stmt->execute($params);
                $questions = $stmt->fetchAll(PDO::FETCH_ASSOC);

                // Decode JSON options for each
                foreach ($questions as &$q) {
                    if ($q['options_json']) {
                        $q['options'] = json_decode($q['options_json'], true);
                    }
                }
                unset($q);

                // Get type/category counts for filters
                $counts = $pdo->query("
                    SELECT type, category, COUNT(*) as count
                    FROM ai_questions
                    WHERE is_active = 1
                    GROUP BY type, category
                ")->fetchAll(PDO::FETCH_ASSOC);

                successResponse([
                    'questions' => $questions,
                    'counts' => $counts
                ]);
            }
            break;

        case 'POST':
            // Create new question
            $input = getJsonInput();

            $required = ['text', 'type', 'input_type'];
            if ($error = validateRequired($required, $input)) {
                errorResponse($error);
            }

            // Validate type
            $valid_types = ['onboarding', 'periodic', 'event', 'followup', 'contextual'];
            if (!in_array($input['type'], $valid_types)) {
                errorResponse('Invalid type. Must be one of: ' . implode(', ', $valid_types));
            }

            // Validate input_type
            $valid_input_types = ['buttons', 'dropdown', 'text', 'number', 'date'];
            if (!in_array($input['input_type'], $valid_input_types)) {
                errorResponse('Invalid input_type. Must be one of: ' . implode(', ', $valid_input_types));
            }

            $options_json = null;
            if (!empty($input['options']) && is_array($input['options'])) {
                $options_json = json_encode($input['options']);
            }

            $stmt = $pdo->prepare("
                INSERT INTO ai_questions
                (text, type, category, input_type, options_json, trigger_condition,
                 priority, frequency, follow_up_to, admin_notes, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ");
            $stmt->execute([
                $input['text'],
                $input['type'],
                $input['category'] ?? null,
                $input['input_type'],
                $options_json,
                $input['trigger_condition'] ?? null,
                $input['priority'] ?? 3,
                $input['frequency'] ?? null,
                $input['follow_up_to'] ?? null,
                $input['admin_notes'] ?? null,
                isset($input['is_active']) ? ($input['is_active'] ? 1 : 0) : 1
            ]);

            $new_id = $pdo->lastInsertId();

            successResponse(['id' => $new_id], 'Question created');
            break;

        case 'PUT':
            // Update existing question
            if (!$id) {
                errorResponse('Question ID required');
            }

            $input = getJsonInput();

            // Check question exists
            $stmt = $pdo->prepare("SELECT id FROM ai_questions WHERE id = ?");
            $stmt->execute([$id]);
            if (!$stmt->fetch()) {
                errorResponse('Question not found', 404);
            }

            $updates = [];
            $params = [];

            $allowed_fields = [
                'text', 'type', 'category', 'input_type', 'trigger_condition',
                'priority', 'frequency', 'follow_up_to', 'admin_notes', 'is_active'
            ];

            foreach ($allowed_fields as $field) {
                if (array_key_exists($field, $input)) {
                    $updates[] = "$field = ?";
                    $params[] = $input[$field];
                }
            }

            // Handle options separately (JSON encode)
            if (array_key_exists('options', $input)) {
                $updates[] = "options_json = ?";
                $params[] = is_array($input['options']) ? json_encode($input['options']) : null;
            }

            if (empty($updates)) {
                errorResponse('No fields to update');
            }

            $params[] = $id;
            $stmt = $pdo->prepare("
                UPDATE ai_questions
                SET " . implode(', ', $updates) . "
                WHERE id = ?
            ");
            $stmt->execute($params);

            successResponse([], 'Question updated');
            break;

        case 'DELETE':
            // Soft delete question
            if (!$id) {
                errorResponse('Question ID required');
            }

            $stmt = $pdo->prepare("UPDATE ai_questions SET is_active = 0 WHERE id = ?");
            $stmt->execute([$id]);

            if ($stmt->rowCount() === 0) {
                errorResponse('Question not found', 404);
            }

            successResponse([], 'Question deleted');
            break;

        default:
            errorResponse('Method not allowed', 405);
    }
} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
