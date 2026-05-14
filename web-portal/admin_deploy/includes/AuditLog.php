<?php
/**
 * Unified audit logger.
 *
 * Writes one row per call into event_log. Used by:
 *   - Pi-facing endpoints in php_deploy/api/* (tier='device')
 *   - Customer-portal API in php_deploy/api/portal/* (tier='portal')
 *   - Customer portal pages in poolai_deploy/* (tier='portal')
 *   - Admin endpoints in admin_deploy/* (tier='admin')
 *   - Cron scripts in php_deploy/scripts/* (tier='system')
 *
 * Failures are swallowed: a broken audit write must never 5xx the caller
 * (especially the Pi heartbeat). Errors go to PHP error_log instead.
 *
 * NOTE: this file is duplicated across all three deploy trees
 * (admin_deploy/, php_deploy/, poolai_deploy/). Keep them in sync — same
 * pattern as auth.php and api_helpers.php.
 */

require_once __DIR__ . '/../config/database.php';

class AuditLog {
    /**
     * Record an event.
     *
     * @param string $tier     'admin' | 'portal' | 'device' | 'system'
     * @param string $action   noun.verb, e.g. 'client.suspend', 'device.heartbeat'
     * @param array|null $actor   ['type' => 'admin|user|device|system|anonymous', 'id' => string|int|null]
     * @param array|null $target  ['type' => 'device|user|subscription|...', 'id' => string|int]
     * @param string $result   'ok' | 'fail' | 'denied'
     * @param array $details   arbitrary JSON-serializable payload
     */
    public static function record(
        string $tier,
        string $action,
        ?array $actor = null,
        ?array $target = null,
        string $result = 'ok',
        array $details = []
    ): void {
        try {
            $pdo = db();
            $stmt = $pdo->prepare("
                INSERT INTO event_log
                    (tier, actor_type, actor_id, action, target_type, target_id, result, details_json, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ");
            $stmt->execute([
                $tier,
                $actor['type'] ?? 'system',
                isset($actor['id']) ? (string)$actor['id'] : null,
                $action,
                $target['type'] ?? null,
                isset($target['id']) ? (string)$target['id'] : null,
                $result,
                $details ? json_encode($details, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) : null,
                self::clientIp(),
                self::userAgent(),
            ]);
        } catch (Throwable $e) {
            error_log('AuditLog::record failed: ' . $e->getMessage() . ' (action=' . $action . ')');
        }
    }

    private static function clientIp(): ?string {
        if (!empty($_SERVER['HTTP_CF_CONNECTING_IP'])) {
            return substr($_SERVER['HTTP_CF_CONNECTING_IP'], 0, 45);
        }
        if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
            $first = trim(explode(',', $_SERVER['HTTP_X_FORWARDED_FOR'])[0]);
            if ($first !== '') return substr($first, 0, 45);
        }
        return isset($_SERVER['REMOTE_ADDR']) ? substr($_SERVER['REMOTE_ADDR'], 0, 45) : null;
    }

    private static function userAgent(): ?string {
        $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
        return $ua !== '' ? substr($ua, 0, 255) : null;
    }
}
