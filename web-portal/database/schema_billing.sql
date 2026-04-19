-- ============================================
-- PoolAIssistant Cloud Integration
-- Billing & Subscription Schema
-- ============================================

-- Subscription plans (Basic, Pro, Enterprise)
CREATE TABLE IF NOT EXISTS subscription_plans (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    price_monthly DECIMAL(8,2) NOT NULL,
    price_yearly DECIMAL(8,2),
    currency VARCHAR(3) DEFAULT 'GBP',
    max_devices INT DEFAULT 1,
    features_json JSON,
    stripe_price_id_monthly VARCHAR(100),
    stripe_price_id_yearly VARCHAR(100),
    is_active TINYINT(1) DEFAULT 1,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_slug (slug),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User subscriptions
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    plan_id INT UNSIGNED NOT NULL,
    stripe_subscription_id VARCHAR(100),
    stripe_customer_id VARCHAR(100),
    status ENUM('active', 'past_due', 'cancelled', 'trialing', 'paused', 'incomplete') DEFAULT 'trialing',
    billing_interval ENUM('monthly', 'yearly') DEFAULT 'monthly',
    current_period_start DATETIME,
    current_period_end DATETIME,
    trial_end DATETIME,
    cancel_at_period_end TINYINT(1) DEFAULT 0,
    cancelled_at DATETIME,
    cancel_reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES subscription_plans(id),
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_stripe_sub (stripe_subscription_id),
    INDEX idx_stripe_cust (stripe_customer_id),
    INDEX idx_period_end (current_period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Payment history
CREATE TABLE IF NOT EXISTS payment_history (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    subscription_id INT UNSIGNED,
    stripe_payment_intent_id VARCHAR(100),
    stripe_invoice_id VARCHAR(100),
    amount DECIMAL(8,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'GBP',
    status ENUM('succeeded', 'failed', 'pending', 'refunded', 'partially_refunded') NOT NULL,
    description VARCHAR(255),
    failure_reason VARCHAR(255),
    receipt_url VARCHAR(500),
    invoice_pdf_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (subscription_id) REFERENCES user_subscriptions(id) ON DELETE SET NULL,
    INDEX idx_user (user_id),
    INDEX idx_subscription (subscription_id),
    INDEX idx_status (status),
    INDEX idx_stripe_payment (stripe_payment_intent_id),
    INDEX idx_stripe_invoice (stripe_invoice_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Stripe webhook events log (for idempotency and debugging)
CREATE TABLE IF NOT EXISTS stripe_webhook_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    payload_json LONGTEXT,
    processed TINYINT(1) DEFAULT 0,
    process_error VARCHAR(500),
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP NULL,
    INDEX idx_event_id (event_id),
    INDEX idx_event_type (event_type),
    INDEX idx_processed (processed),
    INDEX idx_received (received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add subscription-related columns to portal_users
-- Run these ALTER statements if columns don't exist:
-- ALTER TABLE portal_users ADD COLUMN subscription_override ENUM('none', 'comp', 'extended') DEFAULT 'none';
-- ALTER TABLE portal_users ADD COLUMN subscription_override_until DATETIME NULL;
-- ALTER TABLE portal_users ADD COLUMN suspended_reason VARCHAR(255) NULL;
-- ALTER TABLE portal_users ADD COLUMN suspended_at DATETIME NULL;
-- ALTER TABLE portal_users ADD COLUMN suspended_by INT UNSIGNED NULL;

-- ============================================
-- SEED DEFAULT SUBSCRIPTION PLANS
-- ============================================

INSERT INTO subscription_plans (name, slug, description, price_monthly, price_yearly, max_devices, features_json, sort_order)
VALUES
    ('Basic', 'basic', 'Perfect for single pool monitoring', 9.99, 99.00, 1,
     '{"readings_history_days": 30, "email_alerts": true, "ai_suggestions": false, "charts": true, "export_data": false}', 1),

    ('Pro', 'pro', 'For facilities with multiple pools', 24.99, 249.00, 5,
     '{"readings_history_days": 90, "email_alerts": true, "ai_suggestions": true, "charts": true, "export_data": true, "priority_support": false}', 2),

    ('Enterprise', 'enterprise', 'Unlimited pools with full features', 49.99, 499.00, -1,
     '{"readings_history_days": 365, "email_alerts": true, "ai_suggestions": true, "charts": true, "export_data": true, "priority_support": true, "custom_branding": true}', 3)

ON DUPLICATE KEY UPDATE
    description = VALUES(description),
    price_monthly = VALUES(price_monthly),
    price_yearly = VALUES(price_yearly),
    max_devices = VALUES(max_devices),
    features_json = VALUES(features_json);

-- ============================================
-- HELPER VIEWS
-- ============================================

-- View to get user subscription status easily
CREATE OR REPLACE VIEW v_user_subscription_status AS
SELECT
    u.id as user_id,
    u.email,
    u.name,
    u.status as account_status,
    u.subscription_override,
    u.subscription_override_until,
    s.id as subscription_id,
    s.status as subscription_status,
    s.current_period_end,
    s.trial_end,
    s.cancel_at_period_end,
    p.name as plan_name,
    p.slug as plan_slug,
    p.max_devices,
    CASE
        -- Comped accounts always have access
        WHEN u.subscription_override = 'comp' THEN 'active'
        -- Extended trial
        WHEN u.subscription_override = 'extended' AND u.subscription_override_until > NOW() THEN 'active'
        -- Active subscription
        WHEN s.status = 'active' THEN 'active'
        -- Trialing
        WHEN s.status = 'trialing' AND (s.trial_end IS NULL OR s.trial_end > NOW()) THEN 'active'
        -- Past due with grace period (7 days)
        WHEN s.status = 'past_due' AND s.current_period_end > DATE_SUB(NOW(), INTERVAL 7 DAY) THEN 'grace'
        -- No access
        ELSE 'inactive'
    END as access_status
FROM portal_users u
LEFT JOIN user_subscriptions s ON s.user_id = u.id
LEFT JOIN subscription_plans p ON p.id = s.plan_id;
