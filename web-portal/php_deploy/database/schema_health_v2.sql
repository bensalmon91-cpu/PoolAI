-- Device Health Monitoring Schema v2
-- Adds controller status, alarms, and issues tracking
-- Run this migration to add new columns

-- Add new columns to device_health table
ALTER TABLE device_health
    ADD COLUMN controllers_online TINYINT UNSIGNED DEFAULT 0 AFTER ip_address,
    ADD COLUMN controllers_offline TINYINT UNSIGNED DEFAULT 0 AFTER controllers_online,
    ADD COLUMN controllers_json TEXT AFTER controllers_offline,
    ADD COLUMN alarms_total INT UNSIGNED DEFAULT 0 AFTER controllers_json,
    ADD COLUMN alarms_critical INT UNSIGNED DEFAULT 0 AFTER alarms_total,
    ADD COLUMN alarms_warning INT UNSIGNED DEFAULT 0 AFTER alarms_critical,
    ADD COLUMN issues_json TEXT AFTER alarms_warning,
    ADD COLUMN has_issues TINYINT(1) DEFAULT 0 AFTER issues_json;

-- Create index for finding devices with issues
CREATE INDEX idx_has_issues ON device_health(has_issues, ts DESC);

-- Optional: View for latest health per device with issues summary
CREATE OR REPLACE VIEW v_device_health_latest AS
SELECT
    h.*,
    d.name as device_name,
    d.last_seen,
    TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) as minutes_since_seen,
    CASE
        WHEN TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) < 20 THEN 1
        ELSE 0
    END as is_online
FROM device_health h
INNER JOIN (
    SELECT device_id, MAX(ts) as max_ts
    FROM device_health
    GROUP BY device_id
) latest ON h.device_id = latest.device_id AND h.ts = latest.max_ts
JOIN pi_devices d ON h.device_id = d.id
WHERE d.is_active = 1;
