<?php
/**
 * Extra Database Schema - Audit Log Table
 *
 * Upload to FTP root (poolai.modprojects.co.uk) then access:
 * https://poolai.modprojects.co.uk/deploy_schemas_extra.php
 *
 * DELETE THIS FILE AFTER RUNNING.
 */

error_reporting(E_ALL);
ini_set('display_errors', 1);

echo "<pre style='font-family: monospace; background: #1e293b; color: #f1f5f9; padding: 20px;'>";
echo "PoolAIssistant Extra Schema Installer\n";
echo "=====================================\n\n";

// Database credentials - source from the already-installed config on the
// admin backend rather than carrying a literal in this one-shot installer.
$adminConfig = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/config/database.php';
if (file_exists($adminConfig)) {
    require_once $adminConfig;
    $host = defined('DB_HOST') ? DB_HOST : 'localhost';
    $dbname = defined('DB_NAME') ? DB_NAME : '';
    $user = defined('DB_USER') ? DB_USER : '';
    $pass = defined('DB_PASS') ? DB_PASS : '';
} else {
    $host = getenv('DB_HOST') ?: 'localhost';
    $dbname = getenv('DB_NAME') ?: '';
    $user = getenv('DB_USER') ?: '';
    $pass = getenv('DB_PASS') ?: '';
}
if (!$dbname || !$user) {
    die("[ERROR] DB credentials unavailable. Ensure admin backend is deployed or set DB_* env vars.\n");
}

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $user, $pass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    ]);
    echo "[OK] Connected to database\n\n";
} catch (PDOException $e) {
    die("[ERROR] Database connection failed: " . $e->getMessage() . "\n");
}

// Extra schemas to run
$schemas = [
    'portal_audit_log' => '
CREATE TABLE IF NOT EXISTS portal_audit_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NULL,
    action VARCHAR(100) NOT NULL,
    details_json JSON,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
',
    'portal_sessions' => '
CREATE TABLE IF NOT EXISTS portal_sessions (
    id VARCHAR(64) PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
'
];

// Run each schema
foreach ($schemas as $name => $sql) {
    echo "Creating: $name\n";

    try {
        $pdo->exec($sql);
        echo "  [OK] Table created or already exists\n";
    } catch (PDOException $e) {
        if (strpos($e->getMessage(), 'already exists') === false) {
            echo "  [WARN] " . $e->getMessage() . "\n";
        } else {
            echo "  [OK] Table already exists\n";
        }
    }
    echo "\n";
}

echo "=====================================\n";
echo "Extra schema installation complete!\n\n";
echo "DELETE THIS FILE NOW.\n";
echo "</pre>";
