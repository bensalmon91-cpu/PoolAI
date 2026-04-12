-- Performance indexes for PoolAIssistant
-- Run this once against your pool_readings.sqlite3 database
-- This will significantly speed up chart loading and alarm queries

-- CRITICAL: Index for chart queries (pool + point_label + ts)
-- This is the most important index - speeds up chart loading by 10-100x
CREATE INDEX IF NOT EXISTS idx_readings_pool_label_ts
ON readings(pool, point_label, ts);

-- Index for timestamp-only queries (MAX(ts), recent data)
CREATE INDEX IF NOT EXISTS idx_readings_ts
ON readings(ts);

-- Index for alarm queries (active alarms lookup)
CREATE INDEX IF NOT EXISTS idx_alarm_events_pool_active
ON alarm_events(pool, ended_ts, started_ts DESC);

-- Index for alarm history queries
CREATE INDEX IF NOT EXISTS idx_alarm_events_pool_ts
ON alarm_events(pool, started_ts DESC);

-- Analyze tables to update query planner statistics
ANALYZE readings;
ANALYZE alarm_events;

-- Verify indexes were created
SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name;
