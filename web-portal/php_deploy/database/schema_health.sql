-- Device Health Monitoring Schema
-- Run this to add health monitoring tables

-- Device health reports from Pi heartbeats
CREATE TABLE IF NOT EXISTS device_health (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uptime_seconds INT UNSIGNED,
    disk_used_pct DECIMAL(5,2),
    memory_used_pct DECIMAL(5,2),
    cpu_temp DECIMAL(5,2),
    last_upload_success TIMESTAMP NULL,
    last_upload_error VARCHAR(500),
    pending_chunks INT DEFAULT 0,
    failed_uploads INT DEFAULT 0,
    software_version VARCHAR(50),
    ip_address VARCHAR(45),
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_ts (device_id, ts DESC),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device commands queue (for on-demand uploads, restarts, etc.)
CREATE TABLE IF NOT EXISTS device_commands (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    command_type ENUM('upload', 'restart', 'update') NOT NULL,
    payload TEXT,
    status ENUM('pending', 'acknowledged', 'completed', 'failed') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    result TEXT,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_status (device_id, status),
    INDEX idx_pending (device_id, status) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Alert tracking to prevent spam
CREATE TABLE IF NOT EXISTS alert_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_type_sent (device_id, alert_type, sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
