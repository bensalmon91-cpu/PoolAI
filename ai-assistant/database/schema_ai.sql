-- AI Assistant Database Schema
-- Migration script for PoolAIssistant AI integration
-- Run this on Hostinger MySQL after existing schema

-- ============================================================================
-- QUESTION LIBRARY (admin-managed templates)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  text TEXT NOT NULL,
  type ENUM('onboarding', 'periodic', 'event', 'followup', 'contextual') NOT NULL,
  category VARCHAR(50),                    -- water_quality, equipment, maintenance, environment
  input_type ENUM('buttons', 'dropdown', 'text', 'number', 'date') DEFAULT 'buttons',
  options_json TEXT,                       -- JSON array of options for buttons/dropdown
  trigger_condition TEXT,                  -- SQL/logic expression for auto-triggering
  priority TINYINT DEFAULT 3,              -- 1-5, higher = more urgent
  frequency VARCHAR(20),                   -- once, daily, weekly, monthly, on_event
  follow_up_to INT NULL,                   -- parent question id for chains
  admin_notes TEXT,
  is_active TINYINT(1) DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (follow_up_to) REFERENCES ai_questions(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- QUESTION QUEUE (per-device pending/answered questions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_question_queue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id INT UNSIGNED NOT NULL,         -- FK to pi_devices.id
  question_id INT NOT NULL,
  pool VARCHAR(100) DEFAULT '',            -- which pool on multi-pool device
  triggered_by VARCHAR(200),               -- why this question was triggered
  status ENUM('pending', 'delivered', 'answered', 'expired', 'skipped') DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  delivered_at TIMESTAMP NULL,
  answered_at TIMESTAMP NULL,
  expires_at TIMESTAMP NULL,               -- auto-expire old questions
  FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES ai_questions(id) ON DELETE CASCADE,
  INDEX idx_device_status (device_id, status),
  INDEX idx_created (created_at),
  INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- USER RESPONSES (answers to questions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_responses (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id INT UNSIGNED NOT NULL,
  question_id INT NOT NULL,
  queue_id BIGINT NOT NULL,
  pool VARCHAR(100) NOT NULL DEFAULT '',
  answer TEXT NOT NULL,                    -- raw answer text
  answer_json TEXT,                        -- structured answer data (JSON)
  answered_at TIMESTAMP NOT NULL,
  flagged TINYINT(1) DEFAULT 0,            -- admin flagged for review
  admin_notes TEXT,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES ai_questions(id) ON DELETE CASCADE,
  FOREIGN KEY (queue_id) REFERENCES ai_question_queue(id) ON DELETE CASCADE,
  INDEX idx_device_pool (device_id, pool),
  INDEX idx_answered (answered_at),
  INDEX idx_flagged (flagged)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- POOL KNOWLEDGE PROFILES (built from responses + data analysis)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_pool_profiles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id INT UNSIGNED NOT NULL,
  pool VARCHAR(100) NOT NULL DEFAULT '',
  profile_json TEXT NOT NULL,              -- structured profile data
  patterns_json TEXT,                      -- learned patterns from data
  maturity_score TINYINT UNSIGNED DEFAULT 0, -- 0-100, higher = more complete profile
  questions_answered INT UNSIGNED DEFAULT 0, -- count of questions answered
  last_question_at TIMESTAMP NULL,         -- when last question was shown
  last_analysis_at TIMESTAMP NULL,         -- when Claude last analyzed
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY unique_device_pool (device_id, pool),
  FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- AI SUGGESTIONS (generated by Claude)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_suggestions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id INT UNSIGNED NOT NULL,
  pool VARCHAR(100) NOT NULL DEFAULT '',
  suggestion_type VARCHAR(50),             -- water_quality, dosing, maintenance, equipment
  title VARCHAR(200) NOT NULL,
  body TEXT NOT NULL,
  priority TINYINT DEFAULT 3,              -- 1-5
  confidence DECIMAL(3,2),                 -- 0.00 to 1.00
  source_data_json TEXT,                   -- what data triggered this (JSON)
  status ENUM('pending', 'delivered', 'read', 'acted_upon', 'dismissed', 'retracted') DEFAULT 'pending',
  admin_notes TEXT,                        -- admin can add notes
  retracted_at TIMESTAMP NULL,             -- if admin retracts
  retracted_reason TEXT,
  delivered_at TIMESTAMP NULL,
  read_at TIMESTAMP NULL,
  user_action TEXT,                        -- what user did with suggestion
  user_feedback TEXT,                      -- optional user feedback
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
  INDEX idx_device_status (device_id, status),
  INDEX idx_created (created_at),
  INDEX idx_type (suggestion_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- CROSS-POOL NORMS (aggregated statistics for comparison)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_pool_norms (
  id INT AUTO_INCREMENT PRIMARY KEY,
  pool_type VARCHAR(50) NOT NULL,          -- indoor_public, outdoor_private, spa, etc.
  metric VARCHAR(50) NOT NULL,             -- ph_mean, chlorine_std, alarm_rate
  value DECIMAL(10,4) NOT NULL,
  sample_count INT UNSIGNED,
  min_value DECIMAL(10,4),
  max_value DECIMAL(10,4),
  std_dev DECIMAL(10,4),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY unique_type_metric (pool_type, metric)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- AI CONVERSATION LOG (Claude interactions for debugging/audit)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_conversation_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id INT UNSIGNED NULL,             -- NULL for batch/aggregate analysis
  pool VARCHAR(100),
  action_type VARCHAR(50) NOT NULL,        -- analyze_response, generate_suggestion, detect_anomaly
  prompt_summary TEXT,                     -- summary of what was asked (not full prompt)
  response_summary TEXT,                   -- summary of Claude's response
  tokens_used INT UNSIGNED,
  model_version VARCHAR(50),
  duration_ms INT UNSIGNED,                -- how long the API call took
  success TINYINT(1) DEFAULT 1,            -- whether the call succeeded
  error_message TEXT,                      -- error details if failed
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_device (device_id),
  INDEX idx_action (action_type),
  INDEX idx_created (created_at),
  INDEX idx_success (success)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SEED INITIAL ONBOARDING QUESTIONS
-- ============================================================================

INSERT INTO ai_questions (text, type, category, input_type, options_json, priority, frequency, admin_notes) VALUES
-- Pool Type
('What type of pool is this?', 'onboarding', 'environment', 'buttons',
 '["Indoor Public", "Outdoor Public", "Indoor Private", "Outdoor Private", "Spa/Hot Tub", "Hydrotherapy"]',
 1, 'once', 'Essential for establishing baseline norms and comparisons'),

-- Pool Volume
('Approximately what is the pool volume?', 'onboarding', 'environment', 'dropdown',
 '["Under 50,000 litres", "50,000 - 100,000 litres", "100,000 - 250,000 litres", "250,000 - 500,000 litres", "Over 500,000 litres", "Unknown"]',
 1, 'once', 'Needed for dosing calculations and comparisons'),

-- Bather Load
('What is the typical daily bather load?', 'onboarding', 'environment', 'buttons',
 '["Light (under 50)", "Moderate (50-200)", "Heavy (200-500)", "Very Heavy (500+)"]',
 2, 'once', 'Affects chlorine demand and maintenance frequency'),

-- Filtration Type
('What type of filtration system does this pool use?', 'onboarding', 'equipment', 'buttons',
 '["Sand Filter", "DE Filter", "Cartridge Filter", "Glass Media", "Other/Unknown"]',
 2, 'once', 'Affects backwash frequency recommendations'),

-- Dosing System
('How is chemical dosing managed?', 'onboarding', 'equipment', 'buttons',
 '["Fully Automatic", "Semi-Automatic", "Manual Dosing"]',
 2, 'once', 'Determines type of dosing recommendations'),

-- Water Source
('What is the primary water source?', 'onboarding', 'environment', 'buttons',
 '["Mains Water", "Well/Borehole", "Mixed/Other"]',
 3, 'once', 'Affects hardness and mineral considerations'),

-- Controller Brand
('What brand of pool controller is installed?', 'onboarding', 'equipment', 'dropdown',
 '["ezetrol", "Prominent", "Signet", "Siemens", "Grundfos", "Other", "Multiple Brands"]',
 2, 'once', 'Helps interpret readings and provide brand-specific advice'),

-- Probe Calibration
('When were the pH and chlorine probes last calibrated?', 'onboarding', 'maintenance', 'buttons',
 '["Within the last month", "1-3 months ago", "3-6 months ago", "Over 6 months ago", "Not sure"]',
 2, 'once', 'Critical for data accuracy assessment'),

-- Known Issues
('Are there any known ongoing issues with this pool?', 'onboarding', 'maintenance', 'text',
 NULL,
 3, 'once', 'Free text to capture specific challenges'),

-- Periodic: Filter Maintenance
('When was the filter last serviced or backwashed?', 'periodic', 'maintenance', 'buttons',
 '["Today", "Within the last week", "1-2 weeks ago", "Over 2 weeks ago", "Not sure"]',
 3, 'monthly', 'Regular check for filter maintenance'),

-- Periodic: Probe Calibration Check
('Have the probes been calibrated recently?', 'periodic', 'maintenance', 'buttons',
 '["Yes, within the last month", "No, need calibration soon", "Not sure"]',
 3, 'monthly', 'Monthly reminder for calibration'),

-- Event: High pH
('pH has been reading high for an extended period. Have you checked the following?', 'event', 'water_quality', 'buttons',
 '["Checked probe - needs calibration", "Checked probe - looks fine", "Adjusted dosing", "Investigating cause", "Need help"]',
 1, 'on_event', 'Triggered when pH anomaly detected'),

-- Event: Low Chlorine
('Chlorine levels have been lower than expected. What might be causing this?', 'event', 'water_quality', 'buttons',
 '["High bather load recently", "Chemical supply running low", "Dosing system issue", "Hot weather/sun exposure", "Not sure"]',
 1, 'on_event', 'Triggered when chlorine demand anomaly detected'),

-- Contextual: After Backwash
('You recently performed a backwash. How long did the filter pressure take to stabilize?', 'contextual', 'equipment', 'buttons',
 '["Immediately", "Within an hour", "Several hours", "Still not stable", "Did not monitor"]',
 4, 'on_event', 'Learn about filter behavior post-maintenance'),

-- Follow-up: Algae
('You mentioned algae concerns previously. Has the situation improved?', 'followup', 'water_quality', 'buttons',
 '["Yes, fully resolved", "Improving but not clear", "No change", "Getting worse"]',
 2, 'on_event', 'Follow-up to previous algae response');

-- ============================================================================
-- INDEXES FOR COMMON QUERIES
-- ============================================================================

-- For finding pending questions for a device
CREATE INDEX IF NOT EXISTS idx_queue_pending ON ai_question_queue (device_id, status, priority DESC);

-- For analytics queries
CREATE INDEX IF NOT EXISTS idx_responses_date ON ai_responses (answered_at, device_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_date ON ai_suggestions (created_at, device_id);
