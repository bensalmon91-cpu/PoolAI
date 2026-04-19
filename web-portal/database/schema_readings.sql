-- ============================================
-- PoolAIssistant Cloud Integration
-- Device Readings Schema
-- ============================================

-- Latest readings (one row per device per pool per metric)
-- Used for dashboard display - always shows most recent value
CREATE TABLE IF NOT EXISTS device_readings_latest (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT '',
    metric VARCHAR(50) NOT NULL,
    value DECIMAL(10,4),
    unit VARCHAR(20),
    ts DATETIME NOT NULL,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_device_pool_metric (device_id, pool, metric),
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device (device_id),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Historical readings (for charts and trend analysis)
-- Stores all readings over time - automatically cleaned up after 90 days
CREATE TABLE IF NOT EXISTS device_readings_history (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT '',
    metric VARCHAR(50) NOT NULL,
    value DECIMAL(10,4),
    unit VARCHAR(20),
    ts DATETIME NOT NULL,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_ts (device_id, ts),
    INDEX idx_device_metric_ts (device_id, metric, ts),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Daily aggregates for long-term storage (after 90 days, hourly data is averaged to daily)
CREATE TABLE IF NOT EXISTS device_readings_daily (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT '',
    metric VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    min_value DECIMAL(10,4),
    max_value DECIMAL(10,4),
    avg_value DECIMAL(10,4),
    sample_count INT UNSIGNED DEFAULT 0,
    UNIQUE KEY unique_device_pool_metric_date (device_id, pool, metric, date),
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_date (device_id, date),
    INDEX idx_device_metric_date (device_id, metric, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device alarm snapshots (synced from Pi)
CREATE TABLE IF NOT EXISTS device_alarms_current (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL DEFAULT '',
    alarm_source VARCHAR(100) NOT NULL,
    alarm_name VARCHAR(200),
    severity ENUM('info', 'warning', 'critical') DEFAULT 'warning',
    started_at DATETIME NOT NULL,
    acknowledged TINYINT(1) DEFAULT 0,
    acknowledged_by VARCHAR(100),
    acknowledged_at DATETIME,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_device_alarm (device_id, pool, alarm_source),
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device (device_id),
    INDEX idx_severity (severity),
    INDEX idx_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Controller status snapshots
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
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device (device_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Snapshot upload log (for debugging and rate limiting)
CREATE TABLE IF NOT EXISTS device_snapshot_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    readings_count INT UNSIGNED DEFAULT 0,
    alarms_count INT UNSIGNED DEFAULT 0,
    controllers_count INT UNSIGNED DEFAULT 0,
    payload_size INT UNSIGNED,
    ip_address VARCHAR(45),
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_received (device_id, received_at),
    INDEX idx_received (received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- CLEANUP PROCEDURES
-- Run daily via cron to manage data retention
-- ============================================

-- Delete historical readings older than 90 days
-- (Assumes daily aggregates have been computed)
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS cleanup_old_readings()
BEGIN
    DELETE FROM device_readings_history
    WHERE ts < DATE_SUB(NOW(), INTERVAL 90 DAY);

    DELETE FROM device_snapshot_log
    WHERE received_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
END //
DELIMITER ;

-- Aggregate hourly readings into daily summaries
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS aggregate_daily_readings()
BEGIN
    INSERT INTO device_readings_daily (device_id, pool, metric, date, min_value, max_value, avg_value, sample_count)
    SELECT
        device_id,
        pool,
        metric,
        DATE(ts) as date,
        MIN(value) as min_value,
        MAX(value) as max_value,
        AVG(value) as avg_value,
        COUNT(*) as sample_count
    FROM device_readings_history
    WHERE DATE(ts) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)
    GROUP BY device_id, pool, metric, DATE(ts)
    ON DUPLICATE KEY UPDATE
        min_value = VALUES(min_value),
        max_value = VALUES(max_value),
        avg_value = VALUES(avg_value),
        sample_count = VALUES(sample_count);
END //
DELIMITER ;
