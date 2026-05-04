-- ============================================================================
-- consumer_keys: API keys for downstream / analytics callers (NOT Pi devices).
--
-- Background: until 2026-05, the brain analytics box reused a row from the
-- pi_devices table as its API key. That conflated two trust models — Pi keys
-- rotate with provisioning, scope to one device, and have a fleet-wide
-- exposure profile; analytics keys live longer, scope to specific read-only
-- permissions, and want a different rotation cadence and audit trail.
--
-- This table is the right home for non-device callers. Endpoints that should
-- accept consumer keys (e.g. /api/list_chunks.php, /api/chunks_status.php)
-- call authenticateConsumerKey() in includes/api_helpers.php with the
-- specific permission they require.
--
-- The pi_devices auth path is unaffected and remains the only path Pis use.
-- ============================================================================

CREATE TABLE IF NOT EXISTS consumer_keys (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(64)  NOT NULL UNIQUE,        -- 'brain', 'investigator', 'alerting-bot', ...
  api_key      VARCHAR(128) NOT NULL UNIQUE,        -- secret token (recommend 64 hex chars)
  permissions  JSON         NOT NULL,               -- e.g. ["read_chunks","read_health"]
  is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMP    NULL,                   -- touched on each authenticated request
  notes        TEXT         NULL,                   -- admin-facing context
  INDEX idx_active (is_active),
  INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Defined permission strings (extend as needed):
--   read_chunks        — list/download data chunks (replaces brain's old pi-key access)
--   read_health        — read device_health rows (for monitoring dashboards)
--   read_alerts        — read alert state (for status pages)
--   admin_chunks       — delete chunks server-side (currently a Pi-only operation)
