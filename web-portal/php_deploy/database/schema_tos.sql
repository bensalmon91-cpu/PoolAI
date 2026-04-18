-- ============================================================================
-- Terms of Service acceptance tracking on portal_users.
-- Idempotent: safe to run repeatedly.
-- register.php also ALTERs defensively in case this migration hasn't run yet.
-- ============================================================================

ALTER TABLE portal_users
  ADD COLUMN IF NOT EXISTS tos_accepted_at TIMESTAMP NULL,
  ADD COLUMN IF NOT EXISTS tos_accepted_version VARCHAR(32) NULL;

CREATE INDEX IF NOT EXISTS idx_portal_users_tos_accepted_at
  ON portal_users (tos_accepted_at);
