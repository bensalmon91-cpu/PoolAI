<?php
/**
 * Application Configuration
 *
 * Loads configuration from environment variables.
 * Copy .env.example to .env and set your values.
 */

// Prevent direct access
if (!defined('APP_ROOT')) {
    define('APP_ROOT', dirname(__DIR__));
}

// Load .env file if it exists
$envFile = APP_ROOT . '/.env';
if (file_exists($envFile)) {
    $lines = file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (strpos(trim($line), '#') === 0) continue;
        if (strpos($line, '=') === false) continue;
        list($name, $value) = explode('=', $line, 2);
        $name = trim($name);
        $value = trim($value, " \t\n\r\0\x0B\"'");
        if (!getenv($name)) {
            putenv("$name=$value");
            $_ENV[$name] = $value;
        }
    }
}

/**
 * Get environment variable with fallback
 */
function env(string $key, $default = null) {
    $value = getenv($key);
    if ($value === false) {
        return $default;
    }
    // Handle boolean strings
    if (strtolower($value) === 'true') return true;
    if (strtolower($value) === 'false') return false;
    return $value;
}

// Database Configuration
define('DB_HOST', env('DB_HOST', 'localhost'));
define('DB_NAME', env('DB_NAME', ''));
define('DB_USER', env('DB_USER', ''));
define('DB_PASS', env('DB_PASS', ''));

// Validate required config
if (empty(DB_NAME) || empty(DB_USER)) {
    if (php_sapi_name() !== 'cli') {
        http_response_code(500);
        die('Database configuration missing. Check .env file.');
    }
}

// Session Configuration
define('SESSION_NAME', env('SESSION_NAME', 'mod_admin_session'));
define('SESSION_LIFETIME', (int)env('SESSION_LIFETIME', 3600));

// Upload Configuration
define('UPLOAD_DIR', APP_ROOT . '/data/uploads/');
define('UPDATES_DIR', APP_ROOT . '/data/updates/');
define('MAX_UPLOAD_SIZE', (int)env('MAX_UPLOAD_SIZE', 50 * 1024 * 1024));

// Rate Limiting
define('LOGIN_MAX_ATTEMPTS', (int)env('LOGIN_MAX_ATTEMPTS', 5));
define('LOGIN_LOCKOUT_TIME', (int)env('LOGIN_LOCKOUT_TIME', 900));

// Allowed file types for Pi uploads
define('ALLOWED_UPLOAD_TYPES', ['database', 'log', 'image', 'other']);

// Allowed MIME types
define('ALLOWED_MIME_TYPES', [
    'application/octet-stream',
    'application/x-sqlite3',
    'text/plain',
    'text/csv',
    'application/json',
    'image/jpeg',
    'image/png',
    'image/gif',
    'application/zip',
    'application/gzip',
    'application/x-tar'
]);

// Alert email for device failures
define('ALERT_EMAIL', env('ALERT_EMAIL', ''));
define('SMTP_FROM', env('SMTP_FROM', 'PoolDash Alerts <alerts@example.com>'));

// Bootstrap secret for device provisioning
define('BOOTSTRAP_SECRET', env('BOOTSTRAP_SECRET', ''));

// Environment
define('DEBUG_MODE', env('DEBUG_MODE', false));

// Error reporting based on environment
if (DEBUG_MODE) {
    error_reporting(E_ALL);
    ini_set('display_errors', '1');
} else {
    error_reporting(0);
    ini_set('display_errors', '0');
}
