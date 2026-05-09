<?php
/**
 * Lightweight admin audit logger.
 *
 * Auto-included from includes/auth.php via require_once (which prevents
 * double-include). Registers a shutdown function that appends one
 * tab-separated line per request to /admin_audit.log at the chroot/docroot.
 * Direct HTTP access to *.log files is blocked by the top-level .htaccess.
 *
 * Format: ISO_TS \t USER \t STATUS \t METHOD \t URI \t DURATION_MS \t IP
 *
 * NOTE: do NOT add a `function_exists()` guard here. On LiteSpeed/PHP-LSAPI
 * workers, function definitions can persist across requests in the worker
 * process, making the guard short-circuit on the first include of every
 * subsequent request. require_once in auth.php is the only protection
 * needed against re-includes within a single request.
 */

if (PHP_SAPI === 'cli') {
    return;
}

if (!function_exists('_admin_audit_log_path')) {
    function _admin_audit_log_path(): string {
        return __DIR__ . '/../admin_audit.log';
    }
}

if (!function_exists('_admin_audit_write')) {
    function _admin_audit_write(): void {
        $path = _admin_audit_log_path();

        $user = '-';
        if (session_status() === PHP_SESSION_ACTIVE && !empty($_SESSION['admin_username'])) {
            $user = $_SESSION['admin_username'];
        }

        $start = $_SERVER['REQUEST_TIME_FLOAT'] ?? microtime(true);
        $duration_ms = (int) ((microtime(true) - $start) * 1000);

        $line = sprintf(
            "%s\t%s\t%d\t%s\t%s\t%d\t%s\n",
            date('c'),
            $user,
            http_response_code() ?: 0,
            $_SERVER['REQUEST_METHOD'] ?? '-',
            $_SERVER['REQUEST_URI'] ?? '-',
            $duration_ms,
            $_SERVER['REMOTE_ADDR'] ?? '-'
        );

        @file_put_contents($path, $line, FILE_APPEND | LOCK_EX);
    }
}

// Register the shutdown handler. Use a request-scoped static guard - LSAPI
// workers can persist function-table state across requests but each request
// gets a fresh static-variable scope, so this re-registers correctly.
$_admin_audit_registered = $_admin_audit_registered ?? false;
if (!$_admin_audit_registered) {
    register_shutdown_function('_admin_audit_write');
    $_admin_audit_registered = true;
}
