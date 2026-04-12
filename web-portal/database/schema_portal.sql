-- ============================================
-- PoolAIssistant Web Portal - Database Schema
-- Phase 1: Authentication & Device Linking
-- ============================================

-- Customer accounts (separate from admin_users)
CREATE TABLE IF NOT EXISTS portal_users (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    company VARCHAR(200),
    phone VARCHAR(30),
    email_verified TINYINT(1) DEFAULT 0,
    email_verify_token VARCHAR(64),
    email_verify_expires DATETIME,
    password_reset_token VARCHAR(64),
    password_reset_expires DATETIME,
    status ENUM('active', 'suspended', 'pending') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,
    settings_json TEXT,
    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_verify_token (email_verify_token),
    INDEX idx_reset_token (password_reset_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Link users to their Pi devices
CREATE TABLE IF NOT EXISTS user_devices (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    device_id INT UNSIGNED NOT NULL,
    role ENUM('owner', 'viewer', 'manager') DEFAULT 'owner',
    nickname VARCHAR(100),
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_device (user_id, device_id),
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_device (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User sessions for portal
CREATE TABLE IF NOT EXISTS portal_sessions (
    id VARCHAR(64) PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Audit log for security
CREATE TABLE IF NOT EXISTS portal_audit_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED,
    action VARCHAR(50) NOT NULL,
    details_json TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Login attempts for rate limiting
CREATE TABLE IF NOT EXISTS portal_login_attempts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255),
    ip_address VARCHAR(45),
    success TINYINT(1) DEFAULT 0,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email_time (email, attempted_at),
    INDEX idx_ip_time (ip_address, attempted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add link code columns to pi_devices if not exists
-- Run these ALTER statements separately if needed:
-- ALTER TABLE pi_devices ADD COLUMN link_code VARCHAR(20);
-- ALTER TABLE pi_devices ADD COLUMN link_code_expires DATETIME;
-- ALTER TABLE pi_devices ADD COLUMN portal_user_id INT UNSIGNED;

-- Check if columns exist before adding (MySQL 8.0+)
SET @dbname = DATABASE();

SELECT COUNT(*) INTO @col_exists
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname
AND TABLE_NAME = 'pi_devices'
AND COLUMN_NAME = 'link_code';

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE pi_devices ADD COLUMN link_code VARCHAR(20)',
    'SELECT "link_code column already exists"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT COUNT(*) INTO @col_exists
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @dbname
AND TABLE_NAME = 'pi_devices'
AND COLUMN_NAME = 'link_code_expires';

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE pi_devices ADD COLUMN link_code_expires DATETIME',
    'SELECT "link_code_expires column already exists"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
