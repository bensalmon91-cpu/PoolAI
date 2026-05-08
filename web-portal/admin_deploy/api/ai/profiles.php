<?php
/**
 * AI Pool Profiles API - View and manage pool knowledge profiles
 *
 * GET    /api/ai/profiles.php                  - List all profiles
 * GET    /api/ai/profiles.php?device_id=X      - Get profiles for device
 * GET    /api/ai/profiles.php?id=X             - Get single profile
 * PUT    /api/ai/profiles.php?id=X             - Update profile (admin edit)
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
requireAdmin();

$pdo = db();
$method = $_SERVER['REQUEST_METHOD'];
$id = isset($_GET['id']) ? intval($_GET['id']) : null;
$device_id = isset($_GET['device_id']) ? intval($_GET['device_id']) : null;

try {
    switch ($method) {
        case 'GET':
            if ($id) {
                // Get single profile with full details
                $stmt = $pdo->prepare("
                    SELECT p.*,
                           d.name as device_name,
                           d.alias as device_alias,
                           d.device_id as device_uuid
                    FROM ai_pool_profiles p
                    JOIN pi_devices d ON p.device_id = d.id
                    WHERE p.id = ?
                ");
                $stmt->execute([$id]);
                $profile = $stmt->fetch(PDO::FETCH_ASSOC);

                if (!$profile) {
                    errorResponse('Profile not found', 404);
                }

                // Decode JSON fields
                if ($profile['profile_json']) {
                    $profile['profile'] = json_decode($profile['profile_json'], true);
                }
                if ($profile['patterns_json']) {
                    $profile['patterns'] = json_decode($profile['patterns_json'], true);
                }

                // Get recent responses for this device/pool
                $stmt = $pdo->prepare("
                    SELECT r.answer, r.answered_at, q.text as question_text, q.category
                    FROM ai_responses r
                    JOIN ai_questions q ON r.question_id = q.id
                    WHERE r.device_id = ? AND r.pool = ?
                    ORDER BY r.answered_at DESC
                    LIMIT 20
                ");
                $stmt->execute([$profile['device_id'], $profile['pool']]);
                $profile['recent_responses'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

                // Get recent suggestions
                $stmt = $pdo->prepare("
                    SELECT title, status, suggestion_type, created_at
                    FROM ai_suggestions
                    WHERE device_id = ? AND pool = ?
                    ORDER BY created_at DESC
                    LIMIT 10
                ");
                $stmt->execute([$profile['device_id'], $profile['pool']]);
                $profile['recent_suggestions'] = $stmt->fetchAll(PDO::FETCH_ASSOC);

                successResponse(['profile' => $profile]);

            } elseif ($device_id) {
                // Get profiles for specific device
                $stmt = $pdo->prepare("
                    SELECT p.*,
                           d.name as device_name,
                           d.alias as device_alias
                    FROM ai_pool_profiles p
                    JOIN pi_devices d ON p.device_id = d.id
                    WHERE p.device_id = ?
                    ORDER BY p.pool
                ");
                $stmt->execute([$device_id]);
                $profiles = $stmt->fetchAll(PDO::FETCH_ASSOC);

                foreach ($profiles as &$p) {
                    if ($p['profile_json']) {
                        $p['profile'] = json_decode($p['profile_json'], true);
                    }
                }
                unset($p);

                successResponse(['profiles' => $profiles]);

            } else {
                // List all profiles with summary
                $stmt = $pdo->query("
                    SELECT p.id,
                           p.device_id,
                           p.pool,
                           p.maturity_score,
                           p.questions_answered,
                           p.last_question_at,
                           p.last_analysis_at,
                           p.updated_at,
                           d.name as device_name,
                           d.alias as device_alias,
                           JSON_EXTRACT(p.profile_json, '$.type') as pool_type
                    FROM ai_pool_profiles p
                    JOIN pi_devices d ON p.device_id = d.id
                    ORDER BY d.alias, d.name, p.pool
                ");
                $profiles = $stmt->fetchAll(PDO::FETCH_ASSOC);

                // Get maturity distribution
                $maturity_dist = $pdo->query("
                    SELECT
                        CASE
                            WHEN maturity_score < 25 THEN 'new'
                            WHEN maturity_score < 50 THEN 'developing'
                            WHEN maturity_score < 75 THEN 'established'
                            ELSE 'mature'
                        END as level,
                        COUNT(*) as count
                    FROM ai_pool_profiles
                    GROUP BY level
                ")->fetchAll(PDO::FETCH_KEY_PAIR);

                successResponse([
                    'profiles' => $profiles,
                    'total' => count($profiles),
                    'maturity_distribution' => $maturity_dist
                ]);
            }
            break;

        case 'PUT':
            // Update profile
            if (!$id) {
                errorResponse('Profile ID required');
            }

            $input = getJsonInput();

            $stmt = $pdo->prepare("SELECT id, profile_json, patterns_json FROM ai_pool_profiles WHERE id = ?");
            $stmt->execute([$id]);
            $existing = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$existing) {
                errorResponse('Profile not found', 404);
            }

            $updates = [];
            $params = [];

            // Handle profile updates (merge with existing)
            if (isset($input['profile']) && is_array($input['profile'])) {
                $current_profile = $existing['profile_json'] ? json_decode($existing['profile_json'], true) : [];
                $merged = array_merge($current_profile, $input['profile']);
                $updates[] = 'profile_json = ?';
                $params[] = json_encode($merged);
            }

            // Handle patterns updates (merge with existing)
            if (isset($input['patterns']) && is_array($input['patterns'])) {
                $current_patterns = $existing['patterns_json'] ? json_decode($existing['patterns_json'], true) : [];
                $merged = array_merge($current_patterns, $input['patterns']);
                $updates[] = 'patterns_json = ?';
                $params[] = json_encode($merged);
            }

            // Direct field updates
            if (isset($input['maturity_score'])) {
                $updates[] = 'maturity_score = ?';
                $params[] = max(0, min(100, intval($input['maturity_score'])));
            }

            if (empty($updates)) {
                errorResponse('No fields to update');
            }

            $params[] = $id;
            $stmt = $pdo->prepare("
                UPDATE ai_pool_profiles
                SET " . implode(', ', $updates) . "
                WHERE id = ?
            ");
            $stmt->execute($params);

            successResponse([], 'Profile updated');
            break;

        default:
            errorResponse('Method not allowed', 405);
    }
} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
