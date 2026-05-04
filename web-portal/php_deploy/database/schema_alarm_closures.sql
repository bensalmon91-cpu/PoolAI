-- v6.11.12: alarm-closure history with closed_reason from the Pi.
--
-- Pi-side `alarm_events` (SQLite) gained a `closed_reason TEXT` column in
-- v6.11.9 / v6.11.10 to distinguish alarms that ended naturally (NULL =
-- bit observed OFF) from those force-closed by the sweep paths
-- ('controller_offline' = controller offline >= 30 min, 'logger_restart'
-- = startup-clear). Brain reads this via chunks; the customer-portal
-- admin and the AI suggestion stream consume the cloud DB and previously
-- had no way to see the reason.
--
-- This table receives closures pushed in the snapshot payload's
-- alarms.recently_closed field. UNIQUE on (device, pool, host, alarm,
-- ended_ts) so the server is idempotent if the Pi resends a closure.

CREATE TABLE IF NOT EXISTS device_alarm_closures (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) DEFAULT '',
    host VARCHAR(64) DEFAULT '',
    alarm_source VARCHAR(255) NOT NULL,
    started_ts DATETIME,
    ended_ts DATETIME NOT NULL,
    -- 'observed_off' (Pi sent NULL closed_reason — alarm cleared naturally)
    -- 'controller_offline' (force-closed by sweep after >=30 min offline)
    -- 'logger_restart' (force-closed by startup-clear on logger boot)
    closed_reason VARCHAR(50) DEFAULT 'observed_off',
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_close (device_id, pool, host, alarm_source, ended_ts),
    INDEX idx_device_received (device_id, received_at),
    INDEX idx_reason (closed_reason)
);
