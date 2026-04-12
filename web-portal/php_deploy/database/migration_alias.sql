-- Migration: Add alias columns to pi_devices
-- Run this to add device alias/nickname support

-- Add alias column if not exists
ALTER TABLE pi_devices
    ADD COLUMN IF NOT EXISTS alias VARCHAR(100) DEFAULT NULL AFTER name,
    ADD COLUMN IF NOT EXISTS alias_updated_at TIMESTAMP NULL AFTER alias;

-- Create index for alias searches
CREATE INDEX IF NOT EXISTS idx_alias ON pi_devices(alias);

-- Verify migration
SELECT 'Migration complete' as status;
DESCRIBE pi_devices;
