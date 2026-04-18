<?php
/**
 * Portal Database Connection
 *
 * Delegates to the admin backend's database.php when co-located, otherwise
 * loads credentials from a sibling .env file. Never hardcode credentials
 * here - this directory is potentially orphaned and due for removal in
 * Phase 4 cleanup, but until then it must not carry secrets.
 */

$deployConfigPath = __DIR__ . '/../../php_deploy/config/database.php';
$directConfigPath = __DIR__ . '/../../config/database.php';

if (file_exists($deployConfigPath)) {
    require_once $deployConfigPath;
    return;
}
if (file_exists($directConfigPath)) {
    require_once $directConfigPath;
    return;
}

if (!function_exists('db')) {
    $envFile = __DIR__ . '/../.env';
    if (file_exists($envFile)) {
        foreach (file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            $line = ltrim($line);
            if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) continue;
            [$name, $value] = explode('=', $line, 2);
            $name = trim($name);
            $value = trim($value, " \t\n\r\0\x0B\"'");
            if ($name !== '' && getenv($name) === false) {
                putenv("$name=$value");
                $_ENV[$name] = $value;
            }
        }
    }

    if (!defined('DB_HOST')) define('DB_HOST', getenv('DB_HOST') ?: 'localhost');
    if (!defined('DB_NAME')) define('DB_NAME', getenv('DB_NAME') ?: '');
    if (!defined('DB_USER')) define('DB_USER', getenv('DB_USER') ?: '');
    if (!defined('DB_PASS')) define('DB_PASS', getenv('DB_PASS') ?: '');

    function db(): PDO {
        static $pdo = null;
        if ($pdo === null) {
            if (DB_NAME === '' || DB_USER === '') {
                http_response_code(500);
                error_log('web-portal/php: DB credentials missing. Expected web-portal/php/.env');
                die(json_encode(['error' => 'Database configuration missing']));
            }
            $dsn = 'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4';
            $pdo = new PDO($dsn, DB_USER, DB_PASS, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]);
        }
        return $pdo;
    }
}
