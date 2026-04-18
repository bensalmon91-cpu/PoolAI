<?php
/**
 * Fleet health heartbeat alerter.
 *
 * Intended to be run by Hostinger cron every 15 minutes:
 *   */15 * * * * /usr/bin/php /home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/scripts/check_device_health.php
 *
 * Emits an email when a previously-healthy device has missed more than 2x
 * the expected heartbeat interval. State is tracked in staff_checkin-adjacent
 * table `device_alert_state` so we don't re-send on every cron tick.
 *
 * CLI or HTTPS-safe: it refuses to produce output unless invoked from CLI or
 * with an admin session (prevents leaking device state to the internet).
 */

declare(strict_types=1);

require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

$isCli = php_sapi_name() === 'cli';
if (!$isCli) {
    // Allow a browser hit for manual testing, but only for admins.
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

// How long a device may go silent before we consider it missing. Pi uploads
// every ~6 minutes; we alert at 2x interval (12 minutes).
$offline_minutes = 12;

$stmt = $pdo->prepare("
    SELECT d.id, COALESCE(d.alias, d.name, CONCAT('Device ', d.id)) AS display_name,
           d.last_seen,
           TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) AS minutes_since_seen,
           s.last_alert_kind, s.last_alert_at
    FROM pi_devices d
    LEFT JOIN device_alert_state s ON s.device_id = d.id
    WHERE d.is_active = 1
");
$stmt->execute();
$devices = $stmt->fetchAll(PDO::FETCH_ASSOC);

$now = (new DateTimeImmutable('now'))->format('Y-m-d H:i:s');
$to_email = defined('ALERT_EMAIL') && ALERT_EMAIL !== '' ? ALERT_EMAIL : '';
$from = defined('SMTP_FROM') && SMTP_FROM !== '' ? SMTP_FROM : 'PoolAI Alerts <alerts@poolaissistant.modprojects.co.uk>';

$alerts_sent = 0;
$recoveries_logged = 0;

foreach ($devices as $d) {
    $mins = $d['minutes_since_seen'];
    $is_offline = $d['last_seen'] === null || ($mins !== null && (int)$mins >= $offline_minutes);
    $last_kind = $d['last_alert_kind'];

    if ($is_offline && $last_kind !== 'offline') {
        // Transition: healthy -> offline. Send alert.
        if ($to_email) {
            $subject = sprintf('[PoolAI] Device offline: %s', $d['display_name']);
            $body = sprintf(
                "Device '%s' (id=%d) has been offline for %s minutes.\n" .
                "Last seen: %s\n\nAdmin panel: https://poolaissistant.modprojects.co.uk/admin/\n",
                $d['display_name'], (int)$d['id'],
                $mins === null ? 'never-seen' : (string)$mins,
                $d['last_seen'] ?? '(null)'
            );
            $headers = 'From: ' . $from . "\r\nContent-Type: text/plain; charset=utf-8\r\n";
            @mail($to_email, $subject, $body, $headers);
        }
        $pdo->prepare("
            INSERT INTO device_alert_state (device_id, last_alert_kind, last_alert_at)
            VALUES (:id, 'offline', :ts)
            ON DUPLICATE KEY UPDATE last_alert_kind = 'offline', last_alert_at = :ts2
        ")->execute([':id' => $d['id'], ':ts' => $now, ':ts2' => $now]);
        $alerts_sent++;
        echo "ALERT offline: {$d['display_name']} ({$mins} min since seen)\n";
    } elseif (!$is_offline && $last_kind === 'offline') {
        // Transition: offline -> healthy. Log recovery (no email).
        $pdo->prepare("
            UPDATE device_alert_state
            SET last_alert_kind = NULL, last_recovery_at = :ts
            WHERE device_id = :id
        ")->execute([':id' => $d['id'], ':ts' => $now]);
        $recoveries_logged++;
        echo "RECOVERED: {$d['display_name']}\n";
    }
}

echo "\n";
echo sprintf("Checked %d device(s). Alerts sent: %d. Recoveries: %d.\n",
    count($devices), $alerts_sent, $recoveries_logged);

if ($to_email === '') {
    echo "WARN: ALERT_EMAIL not configured in .env; alerts were not mailed.\n";
}
