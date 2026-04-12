<?php
/**
 * Portal Database Connection
 *
 * This includes the main database configuration from php_deploy
 * For deployment, ensure both folders share the same .env file
 */

// When deployed on server, paths are relative to document root
$deployConfigPath = __DIR__ . '/../../php_deploy/config/database.php';
$directConfigPath = __DIR__ . '/../../config/database.php';

if (file_exists($deployConfigPath)) {
    require_once $deployConfigPath;
} elseif (file_exists($directConfigPath)) {
    require_once $directConfigPath;
} else {
    // Fallback: define database connection inline for standalone deployment
    if (!function_exists('db')) {
        // Database credentials - update for production
        if (!defined('DB_HOST')) define('DB_HOST', 'localhost');
        if (!defined('DB_NAME')) define('DB_NAME', 'u931726538_PoolAIssistant');
        if (!defined('DB_USER')) define('DB_USER', 'u931726538_mbs_modproject');
        if (!defined('DB_PASS')) define('DB_PASS', 'PoolAI2026!');

        function db(): PDO {
            static $pdo = null;

            if ($pdo === null) {
                $dsn = 'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4';
                $options = [
                    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                    PDO::ATTR_EMULATE_PREPARES => false,
                ];

                $pdo = new PDO($dsn, DB_USER, DB_PASS, $options);
            }

            return $pdo;
        }
    }
}
