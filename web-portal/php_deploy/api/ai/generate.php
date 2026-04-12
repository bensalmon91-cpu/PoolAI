<?php
/**
 * AI Generate API - Trigger Claude analysis
 *
 * POST /api/ai/generate.php
 * Body: { device_id, pool?, action: "analyze_responses|generate_suggestions|detect_anomalies" }
 *
 * Admin endpoint to manually trigger Claude AI analysis.
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';
require_once __DIR__ . '/../includes/claude_api.php';

setCorsHeaders();
requireAdmin();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

$pdo = db();
$input = getJsonInput();

// Validate required fields
if (empty($input['device_id'])) {
    errorResponse('Missing device_id');
}
if (empty($input['action'])) {
    errorResponse('Missing action');
}

$valid_actions = ['analyze_responses', 'generate_suggestions', 'detect_anomalies'];
if (!in_array($input['action'], $valid_actions)) {
    errorResponse('Invalid action. Must be one of: ' . implode(', ', $valid_actions));
}

$device_id = intval($input['device_id']);
$pool = $input['pool'] ?? '';
$action = $input['action'];

try {
    // Verify device exists
    $stmt = $pdo->prepare("SELECT id, name, alias FROM pi_devices WHERE id = ?");
    $stmt->execute([$device_id]);
    $device = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$device) {
        errorResponse('Device not found', 404);
    }

    // Initialize Claude API
    try {
        $claude = new ClaudeAPI();
    } catch (Exception $e) {
        errorResponse('Claude API not configured: ' . $e->getMessage(), 500);
    }

    // Get pool profile
    $stmt = $pdo->prepare("
        SELECT * FROM ai_pool_profiles WHERE device_id = ? AND pool = ?
    ");
    $stmt->execute([$device_id, $pool]);
    $profile_row = $stmt->fetch(PDO::FETCH_ASSOC);

    $profile = $profile_row && $profile_row['profile_json']
        ? json_decode($profile_row['profile_json'], true)
        : [];

    switch ($action) {
        case 'analyze_responses':
            // Get recent unanalyzed responses
            $stmt = $pdo->prepare("
                SELECT r.*, q.text as question_text, q.type, q.category
                FROM ai_responses r
                JOIN ai_questions q ON r.question_id = q.id
                WHERE r.device_id = ? AND r.pool = ?
                ORDER BY r.answered_at DESC
                LIMIT 10
            ");
            $stmt->execute([$device_id, $pool]);
            $responses = $stmt->fetchAll(PDO::FETCH_ASSOC);

            if (empty($responses)) {
                successResponse(['message' => 'No responses to analyze']);
            }

            $results = [];
            foreach ($responses as $response) {
                $question = [
                    'text' => $response['question_text'],
                    'type' => $response['type'],
                    'category' => $response['category']
                ];

                $analysis = $claude->analyzeResponse(
                    $device_id,
                    $pool,
                    $question,
                    $response['answer'],
                    $profile
                );

                if ($analysis['success'] && !empty($analysis['analysis']['profile_updates'])) {
                    // Merge profile updates
                    $profile = array_merge($profile, $analysis['analysis']['profile_updates']);

                    // Update profile in database
                    $stmt = $pdo->prepare("
                        INSERT INTO ai_pool_profiles (device_id, pool, profile_json, last_analysis_at)
                        VALUES (?, ?, ?, NOW())
                        ON DUPLICATE KEY UPDATE
                            profile_json = VALUES(profile_json),
                            last_analysis_at = NOW()
                    ");
                    $stmt->execute([$device_id, $pool, json_encode($profile)]);
                }

                $results[] = [
                    'response_id' => $response['id'],
                    'analysis' => $analysis
                ];
            }

            successResponse([
                'action' => 'analyze_responses',
                'results' => $results,
                'updated_profile' => $profile
            ]);
            break;

        case 'generate_suggestions':
            // Get recent readings (from device_health as proxy)
            $stmt = $pdo->prepare("
                SELECT * FROM device_health
                WHERE device_id = ?
                ORDER BY ts DESC
                LIMIT 24
            ");
            $stmt->execute([$device_id]);
            $readings = $stmt->fetchAll(PDO::FETCH_ASSOC);

            // Get recent alarms (from health data)
            $alarms = [];
            foreach ($readings as $r) {
                if ($r['alarms_total'] > 0) {
                    $alarms[] = [
                        'timestamp' => $r['ts'],
                        'total' => $r['alarms_total'],
                        'critical' => $r['alarms_critical'],
                        'warning' => $r['alarms_warning']
                    ];
                }
            }

            // Get previous suggestions (to avoid repetition)
            $stmt = $pdo->prepare("
                SELECT title, suggestion_type, created_at
                FROM ai_suggestions
                WHERE device_id = ? AND pool = ?
                ORDER BY created_at DESC
                LIMIT 10
            ");
            $stmt->execute([$device_id, $pool]);
            $previous = $stmt->fetchAll(PDO::FETCH_ASSOC);

            $result = $claude->generateSuggestions(
                $device_id,
                $pool,
                $readings,
                $alarms,
                $profile,
                $previous
            );

            if ($result['success'] && !empty($result['suggestions'])) {
                // Store suggestions
                foreach ($result['suggestions'] as $suggestion) {
                    $stmt = $pdo->prepare("
                        INSERT INTO ai_suggestions
                        (device_id, pool, suggestion_type, title, body, priority, confidence, source_data_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ");
                    $stmt->execute([
                        $device_id,
                        $pool,
                        $suggestion['type'] ?? 'general',
                        $suggestion['title'],
                        $suggestion['body'],
                        $suggestion['priority'] ?? 3,
                        $suggestion['confidence'] ?? 0.8,
                        json_encode(['readings_count' => count($readings), 'alarms_count' => count($alarms)])
                    ]);
                }
            }

            successResponse([
                'action' => 'generate_suggestions',
                'result' => $result,
                'suggestions_created' => count($result['suggestions'] ?? [])
            ]);
            break;

        case 'detect_anomalies':
            // Get pool stats
            $stmt = $pdo->prepare("
                SELECT
                    AVG(disk_used_pct) as avg_disk,
                    AVG(memory_used_pct) as avg_memory,
                    AVG(cpu_temp) as avg_temp,
                    SUM(alarms_total) as total_alarms,
                    SUM(alarms_critical) as total_critical,
                    COUNT(*) as data_points
                FROM device_health
                WHERE device_id = ? AND ts > DATE_SUB(NOW(), INTERVAL 7 DAY)
            ");
            $stmt->execute([$device_id]);
            $pool_stats = $stmt->fetch(PDO::FETCH_ASSOC);

            // Get norms for comparison (if available)
            $pool_type = $profile['type'] ?? 'unknown';
            $stmt = $pdo->prepare("
                SELECT metric, value, std_dev
                FROM ai_pool_norms
                WHERE pool_type = ?
            ");
            $stmt->execute([$pool_type]);
            $norms = $stmt->fetchAll(PDO::FETCH_ASSOC);

            if (empty($norms)) {
                // Use default norms if none exist
                $norms = [
                    ['metric' => 'disk_used_pct', 'value' => 50, 'std_dev' => 15],
                    ['metric' => 'memory_used_pct', 'value' => 60, 'std_dev' => 15],
                    ['metric' => 'cpu_temp', 'value' => 50, 'std_dev' => 10],
                    ['metric' => 'alarm_rate', 'value' => 5, 'std_dev' => 3]
                ];
            }

            $result = $claude->detectAnomalies($device_id, $pool, $pool_stats, $norms);

            // Store anomalies as suggestions if any found
            if ($result['success'] && !empty($result['anomalies'])) {
                foreach ($result['anomalies'] as $anomaly) {
                    if ($anomaly['severity'] !== 'low') {
                        $stmt = $pdo->prepare("
                            INSERT INTO ai_suggestions
                            (device_id, pool, suggestion_type, title, body, priority, source_data_json)
                            VALUES (?, ?, 'anomaly', ?, ?, ?, ?)
                        ");
                        $priority = $anomaly['severity'] === 'high' ? 1 : 2;
                        $stmt->execute([
                            $device_id,
                            $pool,
                            "Anomaly Detected: " . $anomaly['metric'],
                            $anomaly['description'] . "\n\n" . $anomaly['recommendation'],
                            $priority,
                            json_encode(['anomaly' => $anomaly])
                        ]);
                    }
                }
            }

            successResponse([
                'action' => 'detect_anomalies',
                'result' => $result
            ]);
            break;
    }

} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
} catch (Exception $e) {
    errorResponse('Error: ' . $e->getMessage(), 500);
}
