<?php
/**
 * Fleet pipeline health alerter.
 *
 * Detects three independent failure modes per active Pi:
 *   1. offline        - heartbeat itself is silent (the original check)
 *   2. snapshot_stale - heartbeat OK but no /api/device/snapshot.php arrivals
 *   3. chunks_stuck   - heartbeat + snapshot OK, but the chunk uploader is wedged
 *
 * Heartbeat-only monitoring missed the 7-week brain-data silence in
 * 2026-05-04 because chunk_sync.timer wasn't installed on Swanwood and the
 * Pi was heartbeating fine throughout. See project_chunk_pipeline_recovery.
 *
 * Cron (every 15 min):
 *   /usr/bin/php /home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/scripts/check_device_health.php
 *
 * State persisted in `device_alert_state.last_alert_kind`. Edge-triggered:
 * we email only on state changes, not on every cron tick.
 */

declare(strict_types=1);

require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

$isCli = php_sapi_name() === 'cli';
if (!$isCli) {
    requireAdmin();
    header('Content-Type: text/plain; charset=utf-8');
}

$pdo = db();

// Ensure state table exists (idempotent).
$pdo->exec("CREATE TABLE IF NOT EXISTS device_alert_state (
    device_id INT UNSIGNED PRIMARY KEY,
    last_alert_kind VARCHAR(32) NULL,
    last_alert_at TIMESTAMP NULL,
    last_recovery_at TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

// === Tuning ==================================================================
// Each threshold should be >= 2x the cadence of the corresponding upload, so
// a single missed cycle doesn't trip an alert.
$OFFLINE_MINUTES   = 12; // 2x the 6-min snapshot cadence
$SNAPSHOT_MINUTES  = 12; // same - snapshots should land every 6 min
// chunks_stuck needs BOTH conditions: pending_chunks tells us there is work
// to do, and stale-upload tells us it isn't getting done. Either alone gives
// false positives (pending=0 is "genuinely quiet").
$CHUNK_PENDING_MIN = 5;
$CHUNK_STALE_MIN   = 60;
// =============================================================================

/**
 * Pick the highest-priority failure state for a device.
 * offline > snapshot_stale > chunks_stuck > healthy. Priority matters - a
 * snapshot is impossible if the Pi is offline, so we suppress the derived
 * symptom and report only the root cause.
 */
function classify_device(array $d, int $offlineMin, int $snapshotMin, int $chunkPendingMin, int $chunkStaleMin): string {
    if ($d['last_seen'] === null
        || (int)$d['minutes_since_seen'] >= $offlineMin) {
        return 'offline';
    }
    if ($d['minutes_since_snapshot'] === null
        || (int)$d['minutes_since_snapshot'] >= $snapshotMin) {
        return 'snapshot_stale';
    }
    $pending = (int)($d['pending_chunks'] ?? 0);
    $upMins  = $d['minutes_since_chunk_upload'];
    if ($pending >= $chunkPendingMin
        && ($upMins === null || (int)$upMins >= $chunkStaleMin)) {
        return 'chunks_stuck';
    }
    return 'healthy';
}

function format_alert_body(string $state, array $d): string {
    $name = $d['display_name'];
    $id   = (int)$d['id'];
    $admin = "https://poolaissistant.modprojects.co.uk/admin/";

    switch ($state) {
        case 'offline':
            return sprintf(
                "Device '%s' (id=%d) has been offline for %s minutes.\n" .
                "Last seen: %s\n\nAdmin panel: %s\n",
                $name, $id,
                $d['minutes_since_seen'] === null ? 'never-seen' : (string)$d['minutes_since_seen'],
                $d['last_seen'] ?? '(null)', $admin);

        case 'snapshot_stale':
            return sprintf(
                "Device '%s' (id=%d) is heartbeating but no snapshots have arrived in %s minutes.\n" .
                "Heartbeat last seen: %s\nLast snapshot: %s\n\n" .
                "Likely cause: cloud_upload.timer wedged, or POST /api/device/snapshot.php failing.\n\n" .
                "Admin panel: %s\n",
                $name, $id,
                $d['minutes_since_snapshot'] === null ? 'never' : (string)$d['minutes_since_snapshot'],
                $d['last_seen'], $d['last_snapshot'] ?? '(never)', $admin);

        case 'chunks_stuck':
            return sprintf(
                "Device '%s' (id=%d) has %s chunks pending and last successful chunk upload was %s minutes ago.\n" .
                "Heartbeat + snapshots are fine - this is the chunk pipeline only (brain-side data).\n" .
                "Last successful upload: %s\nFailed uploads (lifetime): %s\n\n" .
                "Likely cause: chunk_sync.timer not running, or FTP credentials wrong (cf. 2026-05-04 incident).\n\n" .
                "Admin panel: %s\n",
                $name, $id,
                (string)$d['pending_chunks'],
                $d['minutes_since_chunk_upload'] === null ? 'never' : (string)$d['minutes_since_chunk_upload'],
                $d['last_upload_success'] ?? '(never)',
                (string)$d['failed_uploads'], $admin);
    }
    return sprintf("Device '%s' (id=%d) is in state '%s'.\n", $name, $id, $state);
}

// One query gathers heartbeat freshness, snapshot freshness, and the latest
// device_health row (chunk pipeline state).
$stmt = $pdo->prepare("
    SELECT
        d.id,
        COALESCE(d.alias, d.name, CONCAT('Device ', d.id)) AS display_name,
        d.last_seen,
        TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) AS minutes_since_seen,
        (SELECT MAX(received_at) FROM device_snapshot_log WHERE device_id = d.id) AS last_snapshot,
        TIMESTAMPDIFF(MINUTE,
            (SELECT MAX(received_at) FROM device_snapshot_log WHERE device_id = d.id),
            NOW()) AS minutes_since_snapshot,
        h.last_upload_success,
        TIMESTAMPDIFF(MINUTE, h.last_upload_success, NOW()) AS minutes_since_chunk_upload,
        h.pending_chunks,
        h.failed_uploads,
        s.last_alert_kind, s.last_alert_at
    FROM pi_devices d
    LEFT JOIN device_alert_state s ON s.device_id = d.id
    LEFT JOIN device_health h ON h.id = (
        SELECT id FROM device_health WHERE device_id = d.id ORDER BY id DESC LIMIT 1
    )
    WHERE d.is_active = 1
");
$stmt->execute();
$devices = $stmt->fetchAll(PDO::FETCH_ASSOC);

$now      = (new DateTimeImmutable('now'))->format('Y-m-d H:i:s');
$to_email = defined('ALERT_EMAIL') && ALERT_EMAIL !== '' ? ALERT_EMAIL : '';
$from     = defined('SMTP_FROM') && SMTP_FROM !== ''
    ? SMTP_FROM
    : 'PoolAI Alerts <alerts@poolaissistant.modprojects.co.uk>';

$alerts_sent = 0;
$recoveries_logged = 0;

foreach ($devices as $d) {
    $state = classify_device(
        $d, $OFFLINE_MINUTES, $SNAPSHOT_MINUTES,
        $CHUNK_PENDING_MIN, $CHUNK_STALE_MIN
    );
    $last_kind = $d['last_alert_kind'];

    if ($state === $last_kind) {
        // No transition - stay silent.
        continue;
    }

    if ($state === 'healthy') {
        $pdo->prepare("
            UPDATE device_alert_state
            SET last_alert_kind = NULL, last_recovery_at = :ts
            WHERE device_id = :id
        ")->execute([':id' => $d['id'], ':ts' => $now]);
        $recoveries_logged++;
        echo "RECOVERED ({$last_kind}): {$d['display_name']}\n";
        continue;
    }

    // Any non-healthy transition emails - including failure-mode -> failure-mode.
    if ($to_email) {
        $subject = sprintf('[PoolAI] %s: %s',
            ucfirst(str_replace('_', ' ', $state)),
            $d['display_name']);
        $body = format_alert_body($state, $d);
        $headers = 'From: ' . $from . "\r\nContent-Type: text/plain; charset=utf-8\r\n";
        @mail($to_email, $subject, $body, $headers);
    }

    $pdo->prepare("
        INSERT INTO device_alert_state (device_id, last_alert_kind, last_alert_at)
        VALUES (:id, :kind, :ts)
        ON DUPLICATE KEY UPDATE last_alert_kind = :kind2, last_alert_at = :ts2
    ")->execute([
        ':id' => $d['id'],
        ':kind' => $state, ':kind2' => $state,
        ':ts' => $now, ':ts2' => $now,
    ]);
    $alerts_sent++;
    echo "ALERT {$state}: {$d['display_name']}\n";
}

echo "\n";
echo sprintf("Checked %d device(s). Alerts sent: %d. Recoveries: %d.\n",
    count($devices), $alerts_sent, $recoveries_logged);

if ($to_email === '') {
    echo "WARN: ALERT_EMAIL not configured in .env; alerts were not mailed.\n";
}
