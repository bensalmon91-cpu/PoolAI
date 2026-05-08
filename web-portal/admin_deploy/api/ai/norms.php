<?php
/**
 * AI Pool Norms API - Cross-pool statistics and analytics
 *
 * GET /api/ai/norms.php              - Get all norms
 * GET /api/ai/norms.php?type=X       - Get norms for specific pool type
 * POST /api/ai/norms.php/recalculate - Recalculate norms from data
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
requireAdmin();

$pdo = db();
$method = $_SERVER['REQUEST_METHOD'];

try {
    switch ($method) {
        case 'GET':
            $pool_type = $_GET['type'] ?? null;

            if ($pool_type) {
                // Get norms for specific pool type
                $stmt = $pdo->prepare("
                    SELECT * FROM ai_pool_norms
                    WHERE pool_type = ?
                    ORDER BY metric
                ");
                $stmt->execute([$pool_type]);
            } else {
                // Get all norms
                $stmt = $pdo->query("
                    SELECT * FROM ai_pool_norms
                    ORDER BY pool_type, metric
                ");
            }
            $norms = $stmt->fetchAll(PDO::FETCH_ASSOC);

            // Get pool type counts
            $types = $pdo->query("
                SELECT
                    JSON_UNQUOTE(JSON_EXTRACT(profile_json, '$.type')) as pool_type,
                    COUNT(*) as count
                FROM ai_pool_profiles
                WHERE profile_json IS NOT NULL
                GROUP BY pool_type
            ")->fetchAll(PDO::FETCH_KEY_PAIR);

            successResponse([
                'norms' => $norms,
                'pool_types' => $types
            ]);
            break;

        case 'POST':
            // Check for recalculate action
            $input = getJsonInput();
            $action = $input['action'] ?? '';

            if ($action !== 'recalculate') {
                errorResponse('Unknown action');
            }

            // Recalculate norms from all pool data
            // This would normally aggregate data from device_health and pool profiles

            // For now, calculate basic metrics from device_health
            $metrics = $pdo->query("
                SELECT
                    'all' as pool_type,
                    'disk_used_pct' as metric,
                    AVG(disk_used_pct) as value,
                    COUNT(*) as sample_count,
                    MIN(disk_used_pct) as min_value,
                    MAX(disk_used_pct) as max_value,
                    STDDEV(disk_used_pct) as std_dev
                FROM device_health
                WHERE disk_used_pct IS NOT NULL AND ts > DATE_SUB(NOW(), INTERVAL 30 DAY)

                UNION ALL

                SELECT
                    'all' as pool_type,
                    'memory_used_pct' as metric,
                    AVG(memory_used_pct) as value,
                    COUNT(*) as sample_count,
                    MIN(memory_used_pct) as min_value,
                    MAX(memory_used_pct) as max_value,
                    STDDEV(memory_used_pct) as std_dev
                FROM device_health
                WHERE memory_used_pct IS NOT NULL AND ts > DATE_SUB(NOW(), INTERVAL 30 DAY)

                UNION ALL

                SELECT
                    'all' as pool_type,
                    'cpu_temp' as metric,
                    AVG(cpu_temp) as value,
                    COUNT(*) as sample_count,
                    MIN(cpu_temp) as min_value,
                    MAX(cpu_temp) as max_value,
                    STDDEV(cpu_temp) as std_dev
                FROM device_health
                WHERE cpu_temp IS NOT NULL AND ts > DATE_SUB(NOW(), INTERVAL 30 DAY)

                UNION ALL

                SELECT
                    'all' as pool_type,
                    'alarms_per_day' as metric,
                    AVG(daily_alarms) as value,
                    COUNT(*) as sample_count,
                    MIN(daily_alarms) as min_value,
                    MAX(daily_alarms) as max_value,
                    STDDEV(daily_alarms) as std_dev
                FROM (
                    SELECT DATE(ts) as day, SUM(alarms_total) as daily_alarms
                    FROM device_health
                    WHERE ts > DATE_SUB(NOW(), INTERVAL 30 DAY)
                    GROUP BY DATE(ts), device_id
                ) daily_stats
            ")->fetchAll(PDO::FETCH_ASSOC);

            // Upsert norms
            $stmt = $pdo->prepare("
                INSERT INTO ai_pool_norms
                (pool_type, metric, value, sample_count, min_value, max_value, std_dev)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    value = VALUES(value),
                    sample_count = VALUES(sample_count),
                    min_value = VALUES(min_value),
                    max_value = VALUES(max_value),
                    std_dev = VALUES(std_dev),
                    updated_at = NOW()
            ");

            $updated = 0;
            foreach ($metrics as $m) {
                if ($m['value'] !== null) {
                    $stmt->execute([
                        $m['pool_type'],
                        $m['metric'],
                        $m['value'],
                        $m['sample_count'],
                        $m['min_value'],
                        $m['max_value'],
                        $m['std_dev']
                    ]);
                    $updated++;
                }
            }

            successResponse([
                'message' => "Recalculated $updated metrics"
            ]);
            break;

        default:
            errorResponse('Method not allowed', 405);
    }
} catch (PDOException $e) {
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
