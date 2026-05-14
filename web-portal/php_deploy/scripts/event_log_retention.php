<?php
/**
 * Daily retention sweep for event_log.
 *
 * Different action families have different retention windows so the table
 * stays useful for forensics without growing unbounded. High-volume Pi
 * traffic (heartbeats every minute) gets a short window; admin mutations
 * and billing events get a long window.
 *
 * Cron: 0 4 * * * php /home/u931726538/.../scripts/event_log_retention.php
 *
 * Usage:
 *   php event_log_retention.php            # run for real
 *   php event_log_retention.php --dry-run  # show counts that would be deleted
 *
 * Records a 'system / retention.sweep' event with per-bucket counts and any
 * per-bucket errors so a partial failure is still visible in the audit trail.
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/AuditLog.php';

$dryRun = in_array('--dry-run', $argv, true);
$batchSize = 10000;
$maxIterationsPerBucket = 10;  // 10 × 10000 = 100k row cap per bucket per run

// Retention buckets. Anything not matched here falls into the catch-all
// (last entry) so newly-introduced action names default to long retention.
$buckets = [
    [
        'name'  => 'heartbeat_snapshot_ok',
        'days'  => 7,
        'where' => "action IN ('device.heartbeat','device.snapshot','device.chunks_status','device.status_query') AND result = 'ok'",
    ],
    [
        'name'  => 'poll_endpoints',
        'days'  => 14,
        'where' => "action IN ('device.update_poll','portal.link_status_poll','device.chunk_upload') AND result = 'ok'",
    ],
    [
        'name'  => 'portal_navigation',
        'days'  => 90,
        'where' => "action IN ('auth.login','auth.logout','account.update') AND result = 'ok'",
    ],
    [
        'name'  => 'ai_qna',
        'days'  => 90,
        'where' => "action LIKE 'ai.%' AND result = 'ok'",
    ],
    [
        // Auth failures store the attempted email in details_json. Must purge
        // sooner than the long_retention catch-all (PII).
        'name'  => 'auth_failures',
        'days'  => 60,
        'where' => "action = 'auth.login_fail'",
    ],
    [
        'name'  => 'long_retention',
        'days'  => 365,
        // Catch-all: anything not deleted by a prior bucket OR anything failed/denied.
        'where' => "1=1",
    ],
];

$pdo = db();
$results = [];
$errors = [];

foreach ($buckets as $bucket) {
    $bucketName = $bucket['name'];
    $cutoff = $bucket['days'];
    $where  = $bucket['where'];

    try {
        if ($dryRun) {
            $stmt = $pdo->prepare("SELECT COUNT(*) AS n FROM event_log WHERE created_at < (NOW() - INTERVAL :d DAY) AND ($where)");
            $stmt->execute([':d' => $cutoff]);
            $count = (int)$stmt->fetch()['n'];
            $results[$bucketName] = $count;
            echo "[DRY-RUN] {$bucketName} (>{$cutoff}d): would delete $count rows\n";
            continue;
        }

        $totalDeleted = 0;
        $iterations = 0;
        $hitCap = false;
        while ($iterations < $maxIterationsPerBucket) {
            $iterations++;
            $stmt = $pdo->prepare("
                DELETE FROM event_log
                WHERE created_at < (NOW() - INTERVAL :d DAY)
                  AND ($where)
                LIMIT $batchSize
            ");
            $stmt->execute([':d' => $cutoff]);
            $rows = $stmt->rowCount();
            $totalDeleted += $rows;
            if ($rows < $batchSize) {
                break;
            }
            if ($iterations === $maxIterationsPerBucket && $rows === $batchSize) {
                $hitCap = true;
            }
        }
        $results[$bucketName] = $totalDeleted;
        echo "Deleted $totalDeleted rows from bucket {$bucketName} (>{$cutoff}d)\n";
        if ($hitCap) {
            $errors[$bucketName] = "hit iteration cap ($maxIterationsPerBucket × $batchSize); backlog remains";
            echo "  WARNING: bucket {$bucketName} hit iteration cap, backlog remains\n";
        }
    } catch (Throwable $e) {
        $errors[$bucketName] = $e->getMessage();
        error_log("event_log_retention bucket '{$bucketName}' failed: " . $e->getMessage());
        echo "ERROR in bucket {$bucketName}: " . $e->getMessage() . "\n";
    }
}

if (!$dryRun) {
    AuditLog::record(
        'system',
        'retention.sweep',
        ['type' => 'system', 'id' => 'event_log_retention'],
        null,
        empty($errors) ? 'ok' : 'fail',
        ['deleted' => $results, 'errors' => $errors]
    );
}
