-- ============================================================================
-- STAFF PWA SCHEMA
-- Staff check-ins log used by the staff PWA to record "all clear" sign-offs
-- and notes while governing AI activity.
-- ============================================================================

CREATE TABLE IF NOT EXISTS staff_checkins (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  admin_id INT NOT NULL,
  admin_username VARCHAR(100) NOT NULL,
  status ENUM('ok', 'attention', 'issue') NOT NULL DEFAULT 'ok',
  note TEXT,
  devices_online INT DEFAULT NULL,
  devices_offline INT DEFAULT NULL,
  devices_with_issues INT DEFAULT NULL,
  pending_suggestions INT DEFAULT NULL,
  flagged_responses INT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_admin (admin_id),
  INDEX idx_created (created_at),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
