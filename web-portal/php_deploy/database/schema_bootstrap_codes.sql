-- ============================================================================
-- Per-device bootstrap codes.
--
-- The existing single shared BOOTSTRAP_SECRET lets any leaked Pi re-provision
-- (or provision a new one). That's a fleet-wide risk from one compromise.
--
-- This table issues a *single-use* per-device code that an operator enters
-- on the Pi's first-boot setup page. The Pi exchanges the code for a
-- long-lived API key via the existing provision.php flow, at which point
-- the code is marked used. The shared secret stays only as server-side
-- meta-auth between deploy and this table; it's no longer a field credential.
-- ============================================================================

CREATE TABLE IF NOT EXISTS bootstrap_codes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  code_hash CHAR(64) NOT NULL UNIQUE,            -- SHA-256 of the plaintext code
  device_uuid VARCHAR(64) NULL,                  -- populated on first use
  label VARCHAR(200) NOT NULL,                   -- e.g. "Pool 3 replacement" (admin-facing)
  issued_by_admin_id INT NULL,                   -- FK admin_users.id
  issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NULL,                     -- optional expiry
  used_at TIMESTAMP NULL,                        -- when exchanged for an api_key
  used_ip VARCHAR(64) NULL,
  revoked_at TIMESTAMP NULL,
  revoked_reason TEXT NULL,
  INDEX idx_issued (issued_at),
  INDEX idx_used (used_at),
  INDEX idx_device (device_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
