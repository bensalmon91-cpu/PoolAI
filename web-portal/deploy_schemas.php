<?php
/**
 * Database Schema Installer
 *
 * Upload to FTP root (poolai.modprojects.co.uk) then access via browser:
 * https://poolai.modprojects.co.uk/deploy_schemas.php
 *
 * This will install the cloud integration database tables.
 * DELETE THIS FILE AFTER RUNNING.
 */

error_reporting(E_ALL);
ini_set('display_errors', 1);

echo "<pre style='font-family: monospace; background: #1e293b; color: #f1f5f9; padding: 20px;'>";
echo "PoolAIssistant Schema Installer\n";
echo "================================\n\n";

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

// Schema files to run (in order)
$schemas = [
    'schema_readings.sql' => '
-- Device readings latest
CREATE TABLE IF NOT EXISTS device_readings_latest (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT \'\',
    metric VARCHAR(50) NOT NULL,
    value DECIMAL(10,4),
    unit VARCHAR(20),
    ts DATETIME NOT NULL,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_device_pool_metric (device_id, pool, metric),
    INDEX idx_device (device_id),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device readings history
CREATE TABLE IF NOT EXISTS device_readings_history (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT \'\',
    metric VARCHAR(50) NOT NULL,
    value DECIMAL(10,4),
    unit VARCHAR(20),
    ts DATETIME NOT NULL,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_ts (device_id, ts),
    INDEX idx_device_metric_ts (device_id, metric, ts),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device readings daily aggregates
CREATE TABLE IF NOT EXISTS device_readings_daily (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT \'\',
    metric VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    min_value DECIMAL(10,4),
    max_value DECIMAL(10,4),
    avg_value DECIMAL(10,4),
    sample_count INT UNSIGNED DEFAULT 0,
    UNIQUE KEY unique_device_pool_metric_date (device_id, pool, metric, date),
    INDEX idx_device_date (device_id, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device alarms current
CREATE TABLE IF NOT EXISTS device_alarms_current (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT \'\',
    alarm_source VARCHAR(100) NOT NULL,
    alarm_name VARCHAR(200),
    severity ENUM(\'info\', \'warning\', \'critical\') DEFAULT \'warning\',
    started_at DATETIME NOT NULL,
    acknowledged TINYINT(1) DEFAULT 0,
    acknowledged_by VARCHAR(100),
    acknowledged_at DATETIME,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_device_alarm (device_id, pool, alarm_source),
    INDEX idx_device (device_id),
    INDEX idx_severity (severity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device controllers status
CREATE TABLE IF NOT EXISTS device_controllers_status (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    host VARCHAR(100) NOT NULL,
    name VARCHAR(100),
    is_online TINYINT(1) DEFAULT 0,
    last_reading_at DATETIME,
    minutes_ago INT,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_device_controller (device_id, host),
    INDEX idx_device (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Snapshot upload log
CREATE TABLE IF NOT EXISTS device_snapshot_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    readings_count INT UNSIGNED DEFAULT 0,
    alarms_count INT UNSIGNED DEFAULT 0,
    controllers_count INT UNSIGNED DEFAULT 0,
    payload_size INT UNSIGNED,
    ip_address VARCHAR(45),
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_received (device_id, received_at),
    INDEX idx_received (received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
',

    'schema_billing.sql' => '
-- Subscription plans
CREATE TABLE IF NOT EXISTS subscription_plans (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    price_monthly DECIMAL(8,2) NOT NULL,
    price_yearly DECIMAL(8,2),
    currency VARCHAR(3) DEFAULT \'GBP\',
    max_devices INT DEFAULT 1,
    features_json JSON,
    stripe_price_id_monthly VARCHAR(100),
    stripe_price_id_yearly VARCHAR(100),
    is_active TINYINT(1) DEFAULT 1,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_slug (slug),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User subscriptions
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    plan_id INT UNSIGNED NOT NULL,
    stripe_subscription_id VARCHAR(100),
    stripe_customer_id VARCHAR(100),
    status ENUM(\'active\', \'past_due\', \'cancelled\', \'trialing\', \'paused\', \'incomplete\') DEFAULT \'trialing\',
    billing_interval ENUM(\'monthly\', \'yearly\') DEFAULT \'monthly\',
    current_period_start DATETIME,
    current_period_end DATETIME,
    trial_end DATETIME,
    cancel_at_period_end TINYINT(1) DEFAULT 0,
    cancelled_at DATETIME,
    cancel_reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_stripe_sub (stripe_subscription_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Payment history
CREATE TABLE IF NOT EXISTS payment_history (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    subscription_id INT UNSIGNED,
    stripe_payment_intent_id VARCHAR(100),
    stripe_invoice_id VARCHAR(100),
    amount DECIMAL(8,2) NOT NULL,
    currency VARCHAR(3) DEFAULT \'GBP\',
    status ENUM(\'succeeded\', \'failed\', \'pending\', \'refunded\', \'partially_refunded\') NOT NULL,
    description VARCHAR(255),
    failure_reason VARCHAR(255),
    receipt_url VARCHAR(500),
    invoice_pdf_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Stripe webhook log
CREATE TABLE IF NOT EXISTS stripe_webhook_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    payload_json LONGTEXT,
    processed TINYINT(1) DEFAULT 0,
    process_error VARCHAR(500),
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP NULL,
    INDEX idx_event_id (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed subscription plans
INSERT INTO subscription_plans (name, slug, description, price_monthly, price_yearly, max_devices, features_json, sort_order)
VALUES
    (\'Basic\', \'basic\', \'Perfect for single pool monitoring\', 9.99, 99.00, 1,
     \'{"readings_history_days": 30, "email_alerts": true, "ai_suggestions": false}\', 1),
    (\'Pro\', \'pro\', \'For facilities with multiple pools\', 24.99, 249.00, 5,
     \'{"readings_history_days": 90, "email_alerts": true, "ai_suggestions": true}\', 2),
    (\'Enterprise\', \'enterprise\', \'Unlimited pools with full features\', 49.99, 499.00, -1,
     \'{"readings_history_days": 365, "email_alerts": true, "ai_suggestions": true, "priority_support": true}\', 3)
ON DUPLICATE KEY UPDATE name = VALUES(name);
',

    'schema_coupons.sql' => '
-- Coupons
CREATE TABLE IF NOT EXISTS coupons (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    type ENUM(\'free_trial\', \'discount\', \'free_forever\') NOT NULL,
    discount_percent INT UNSIGNED DEFAULT 0,
    duration_days INT UNSIGNED DEFAULT 30,
    max_uses INT UNSIGNED DEFAULT 1,
    current_uses INT UNSIGNED DEFAULT 0,
    valid_from DATETIME DEFAULT CURRENT_TIMESTAMP,
    valid_until DATETIME,
    plan_restriction INT UNSIGNED NULL,
    notes VARCHAR(255),
    created_by INT UNSIGNED,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_code (code),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Coupon redemptions
CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    coupon_id INT UNSIGNED NOT NULL,
    user_id INT UNSIGNED NOT NULL,
    redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    status ENUM(\'active\', \'expired\', \'revoked\') DEFAULT \'active\',
    stripe_coupon_id VARCHAR(100),
    notes VARCHAR(255),
    UNIQUE KEY unique_coupon_user (coupon_id, user_id),
    INDEX idx_user (user_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed test coupons
INSERT INTO coupons (code, type, discount_percent, duration_days, max_uses, notes) VALUES
    (\'DEVTEST\', \'free_forever\', 100, 36500, 10, \'Development testing - permanent free access\'),
    (\'BETA2026\', \'free_trial\', 0, 180, 100, \'Beta tester program - 6 month free trial\'),
    (\'PARTNER50\', \'discount\', 50, 365, 50, \'Partner program - 50% discount for 1 year\'),
    (\'EARLYADOPT\', \'free_trial\', 0, 30, 500, \'Early adopter bonus - 30 day extended trial\')
ON DUPLICATE KEY UPDATE notes = VALUES(notes);
',

    'alter_portal_users.sql' => '
-- Add subscription columns to portal_users if they don\'t exist
-- These are safe to run multiple times

SET @dbname = DATABASE();

-- subscription_override column
SELECT COUNT(*) INTO @col_exists FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = \'portal_users\' AND COLUMN_NAME = \'subscription_override\';
SET @sql = IF(@col_exists = 0,
    \'ALTER TABLE portal_users ADD COLUMN subscription_override ENUM(\\\'none\\\', \\\'comp\\\', \\\'extended\\\') DEFAULT \\\'none\\\'\',
    \'SELECT 1\');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- subscription_override_until column
SELECT COUNT(*) INTO @col_exists FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = \'portal_users\' AND COLUMN_NAME = \'subscription_override_until\';
SET @sql = IF(@col_exists = 0,
    \'ALTER TABLE portal_users ADD COLUMN subscription_override_until DATETIME NULL\',
    \'SELECT 1\');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- suspended_reason column
SELECT COUNT(*) INTO @col_exists FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = \'portal_users\' AND COLUMN_NAME = \'suspended_reason\';
SET @sql = IF(@col_exists = 0,
    \'ALTER TABLE portal_users ADD COLUMN suspended_reason VARCHAR(255) NULL\',
    \'SELECT 1\');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- suspended_at column
SELECT COUNT(*) INTO @col_exists FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = \'portal_users\' AND COLUMN_NAME = \'suspended_at\';
SET @sql = IF(@col_exists = 0,
    \'ALTER TABLE portal_users ADD COLUMN suspended_at DATETIME NULL\',
    \'SELECT 1\');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- suspended_by column
SELECT COUNT(*) INTO @col_exists FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = \'portal_users\' AND COLUMN_NAME = \'suspended_by\';
SET @sql = IF(@col_exists = 0,
    \'ALTER TABLE portal_users ADD COLUMN suspended_by INT UNSIGNED NULL\',
    \'SELECT 1\');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
'
];

// Run each schema
foreach ($schemas as $name => $sql) {
    echo "Running: $name\n";
    echo str_repeat('-', 50) . "\n";

    // Split into individual statements
    $statements = array_filter(array_map('trim', explode(';', $sql)));

    $success = 0;
    $errors = 0;

    foreach ($statements as $statement) {
        if (empty($statement) || $statement === 'SELECT 1') continue;

        try {
            $pdo->exec($statement);
            $success++;
        } catch (PDOException $e) {
            // Ignore "already exists" errors
            if (strpos($e->getMessage(), 'already exists') === false &&
                strpos($e->getMessage(), 'Duplicate') === false) {
                echo "  [WARN] " . $e->getMessage() . "\n";
                $errors++;
            } else {
                $success++; // Count as success if already exists
            }
        }
    }

    echo "  [OK] $success statements executed";
    if ($errors > 0) echo ", $errors warnings";
    echo "\n\n";
}

echo "================================\n";
echo "Schema installation complete!\n\n";
echo "IMPORTANT: Delete this file now:\n";
echo "  rm deploy_schemas.php\n";
echo "</pre>";

// Optionally self-delete (uncomment to enable)
// unlink(__FILE__);
// echo "<p style='color: green;'>This file has been deleted.</p>";
