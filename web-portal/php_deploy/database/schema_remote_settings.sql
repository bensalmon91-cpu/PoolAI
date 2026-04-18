-- ============================================================================
-- Remote-settings feature: admin pushes selected pooldash settings to a
-- specific Pi; Pi reports its current values back on heartbeat so the
-- admin UI shows live state. Re-uses device_commands (payload JSON column
-- already supports arbitrary data); adds a snapshot column on pi_devices
-- so we don't have to walk device_health to get "current settings".
-- ============================================================================

ALTER TABLE pi_devices
  ADD COLUMN IF NOT EXISTS settings_snapshot_json TEXT NULL,
  ADD COLUMN IF NOT EXISTS settings_snapshot_at TIMESTAMP NULL;
