-- Mobile App Database Schema
-- Migration script for PoolAIssistant Mobile App
-- Run this on Hostinger MySQL after existing schema

-- ============================================================================
-- MOBILE AUTH TOKENS (JWT tracking for refresh/revocation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mobile_tokens (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    token_hash VARCHAR(64) NOT NULL,           -- SHA256 of refresh token
    device_info VARCHAR(500),                   -- Device name/model from app
    platform ENUM('ios', 'android') NOT NULL,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP NULL,
    last_used_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_token (token_hash),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- PUSH NOTIFICATION TOKENS (FCM tokens for iOS/Android)
-- ============================================================================

CREATE TABLE IF NOT EXISTS push_tokens (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    fcm_token VARCHAR(500) NOT NULL,
    platform ENUM('ios', 'android') NOT NULL,
    device_info VARCHAR(500),
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_fcm (fcm_token),
    INDEX idx_user (user_id),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- PUSH NOTIFICATION HISTORY (sent notifications log)
-- ============================================================================

CREATE TABLE IF NOT EXISTS push_notifications (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    device_id INT UNSIGNED NULL,               -- Related pi_device if applicable
    type VARCHAR(50) NOT NULL,                  -- alarm, suggestion, device_offline, etc.
    title VARCHAR(200) NOT NULL,
    body TEXT,
    data_json TEXT,                             -- Additional payload data
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP NULL,
    clicked_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    INDEX idx_user_sent (user_id, sent_at),
    INDEX idx_type (type),
    INDEX idx_device (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- USER-DEVICE LINKS (which users can access which devices)
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_device_links (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    device_id INT UNSIGNED NOT NULL,
    role ENUM('owner', 'operator', 'viewer') DEFAULT 'operator',
    nickname VARCHAR(100),                      -- User's custom name for the device
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    linked_by INT UNSIGNED NULL,                -- Who created this link (user_id or NULL for self)
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_device (user_id, device_id),
    INDEX idx_user (user_id),
    INDEX idx_device (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DEVICE LINK CODES (temporary codes for linking devices to accounts)
-- ============================================================================

CREATE TABLE IF NOT EXISTS device_link_codes (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    code VARCHAR(8) NOT NULL,                   -- Short code displayed on Pi (e.g., "ABC123")
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,              -- Typically 15 minutes
    used_at TIMESTAMP NULL,
    used_by INT UNSIGNED NULL,                  -- portal_users.id who used the code
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    UNIQUE KEY unique_code (code),
    INDEX idx_device (device_id),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- USER NOTIFICATION PREFERENCES
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_notification_prefs (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    device_id INT UNSIGNED NULL,                -- NULL = global preference, device_id = per-device
    notify_alarms TINYINT(1) DEFAULT 1,
    notify_suggestions TINYINT(1) DEFAULT 1,
    notify_device_offline TINYINT(1) DEFAULT 1,
    notify_maintenance_due TINYINT(1) DEFAULT 1,
    quiet_hours_start TIME NULL,                -- e.g., 22:00
    quiet_hours_end TIME NULL,                  -- e.g., 07:00
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_device (user_id, device_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- INDEXES FOR COMMON QUERIES
-- ============================================================================

-- For token cleanup (remove expired tokens)
CREATE INDEX IF NOT EXISTS idx_tokens_cleanup ON mobile_tokens (expires_at, revoked_at);

-- For finding user's devices quickly
CREATE INDEX IF NOT EXISTS idx_links_user ON user_device_links (user_id, role);

-- ============================================================================
-- CLEANUP PROCEDURES
-- ============================================================================

-- Procedure to clean up expired tokens (run daily via cron)
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS cleanup_expired_tokens()
BEGIN
    -- Delete expired and revoked tokens older than 30 days
    DELETE FROM mobile_tokens
    WHERE (expires_at < NOW() OR revoked_at IS NOT NULL)
    AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

    -- Delete expired link codes
    DELETE FROM device_link_codes
    WHERE expires_at < NOW()
    AND created_at < DATE_SUB(NOW(), INTERVAL 1 DAY);
END //
DELIMITER ;

-- ============================================================================
-- MIGRATION HELPERS
-- ============================================================================

-- Add phone column to portal_users if not exists
ALTER TABLE portal_users ADD COLUMN IF NOT EXISTS phone VARCHAR(20) NULL AFTER company;

-- Add notification preferences default for existing users
INSERT IGNORE INTO user_notification_prefs (user_id)
SELECT id FROM portal_users WHERE id NOT IN (SELECT user_id FROM user_notification_prefs WHERE device_id IS NULL);
