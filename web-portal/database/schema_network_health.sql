-- ============================================
-- PoolAIssistant - Network Health Column
-- Adds network_json to device_health for per-heartbeat connectivity snapshots.
-- Safe to run multiple times (IF NOT EXISTS guard via information_schema).
-- ============================================

-- Idempotent: only add column if it's not there yet.
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'device_health'
      AND column_name = 'network_json'
);

SET @ddl := IF(
    @col_exists = 0,
    'ALTER TABLE device_health ADD COLUMN network_json JSON NULL AFTER issues_json',
    'SELECT "network_json already exists" AS note'
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
