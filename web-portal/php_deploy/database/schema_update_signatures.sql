-- ============================================================================
-- Ed25519 signatures for software_updates rows.
-- Optional field; Pi verification also works by fetching <url>.sig directly
-- from the updates data dir. This column is the source of truth so the
-- admin UI can show whether a release is signed.
-- ============================================================================

ALTER TABLE software_updates
  ADD COLUMN IF NOT EXISTS signature_b64 TEXT NULL,
  ADD COLUMN IF NOT EXISTS signature_key_fpr VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS signed_at TIMESTAMP NULL;
