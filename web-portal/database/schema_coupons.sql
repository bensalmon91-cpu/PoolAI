-- ============================================
-- PoolAIssistant Cloud Integration
-- Coupon & Promo Code Schema
-- ============================================

-- Coupon codes
CREATE TABLE IF NOT EXISTS coupons (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    type ENUM('free_trial', 'discount', 'free_forever') NOT NULL,
    discount_percent INT UNSIGNED DEFAULT 0,
    duration_days INT UNSIGNED DEFAULT 30,
    max_uses INT UNSIGNED DEFAULT 1,
    current_uses INT UNSIGNED DEFAULT 0,
    valid_from DATETIME DEFAULT CURRENT_TIMESTAMP,
    valid_until DATETIME,
    plan_restriction INT UNSIGNED NULL,
    notes VARCHAR(255),
    created_by INT UNSIGNED,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_restriction) REFERENCES subscription_plans(id) ON DELETE SET NULL,
    INDEX idx_code (code),
    INDEX idx_type (type),
    INDEX idx_active (is_active),
    INDEX idx_valid (valid_from, valid_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Coupon redemptions
CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    coupon_id INT UNSIGNED NOT NULL,
    user_id INT UNSIGNED NOT NULL,
    redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    status ENUM('active', 'expired', 'revoked') DEFAULT 'active',
    stripe_coupon_id VARCHAR(100),
    notes VARCHAR(255),
    FOREIGN KEY (coupon_id) REFERENCES coupons(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_coupon_user (coupon_id, user_id),
    INDEX idx_user (user_id),
    INDEX idx_status (status),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- SEED TEST COUPONS
-- ============================================

-- Development/testing coupon - permanent free access
INSERT INTO coupons (code, type, discount_percent, duration_days, max_uses, notes)
VALUES ('DEVTEST', 'free_forever', 100, 36500, 10, 'Development and testing - permanent free access')
ON DUPLICATE KEY UPDATE notes = VALUES(notes);

-- Beta tester coupon - 180 day free trial
INSERT INTO coupons (code, type, discount_percent, duration_days, max_uses, notes)
VALUES ('BETA2026', 'free_trial', 0, 180, 100, 'Beta tester program - 6 month free trial')
ON DUPLICATE KEY UPDATE notes = VALUES(notes);

-- Partner discount coupon - 50% off for 1 year
INSERT INTO coupons (code, type, discount_percent, duration_days, max_uses, notes)
VALUES ('PARTNER50', 'discount', 50, 365, 50, 'Partner program - 50% discount for 1 year')
ON DUPLICATE KEY UPDATE notes = VALUES(notes);

-- Early adopter coupon - 30 day extended trial
INSERT INTO coupons (code, type, discount_percent, duration_days, max_uses, notes)
VALUES ('EARLYADOPT', 'free_trial', 0, 30, 500, 'Early adopter bonus - 30 day extended trial')
ON DUPLICATE KEY UPDATE notes = VALUES(notes);

-- ============================================
-- HELPER VIEW
-- ============================================

-- View to get active coupon redemptions for a user
CREATE OR REPLACE VIEW v_active_coupon_redemptions AS
SELECT
    r.id as redemption_id,
    r.user_id,
    r.redeemed_at,
    r.expires_at,
    r.status,
    c.id as coupon_id,
    c.code,
    c.type as coupon_type,
    c.discount_percent,
    c.duration_days,
    c.notes as coupon_notes
FROM coupon_redemptions r
JOIN coupons c ON c.id = r.coupon_id
WHERE r.status = 'active'
  AND (r.expires_at IS NULL OR r.expires_at > NOW());

-- ============================================
-- STORED PROCEDURES
-- ============================================

DELIMITER //

-- Redeem a coupon code
CREATE PROCEDURE IF NOT EXISTS redeem_coupon(
    IN p_user_id INT UNSIGNED,
    IN p_code VARCHAR(20),
    OUT p_success TINYINT,
    OUT p_message VARCHAR(255)
)
BEGIN
    DECLARE v_coupon_id INT UNSIGNED;
    DECLARE v_coupon_type VARCHAR(20);
    DECLARE v_duration_days INT UNSIGNED;
    DECLARE v_max_uses INT UNSIGNED;
    DECLARE v_current_uses INT UNSIGNED;
    DECLARE v_valid_until DATETIME;
    DECLARE v_existing_redemption INT UNSIGNED;

    SET p_success = 0;
    SET p_message = '';

    -- Find the coupon
    SELECT id, type, duration_days, max_uses, current_uses, valid_until
    INTO v_coupon_id, v_coupon_type, v_duration_days, v_max_uses, v_current_uses, v_valid_until
    FROM coupons
    WHERE code = UPPER(p_code)
      AND is_active = 1
      AND valid_from <= NOW()
    LIMIT 1;

    IF v_coupon_id IS NULL THEN
        SET p_message = 'Invalid or inactive coupon code';
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid or inactive coupon code';
    END IF;

    -- Check expiration
    IF v_valid_until IS NOT NULL AND v_valid_until < NOW() THEN
        SET p_message = 'Coupon has expired';
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Coupon has expired';
    END IF;

    -- Check usage limit
    IF v_max_uses IS NOT NULL AND v_current_uses >= v_max_uses THEN
        SET p_message = 'Coupon usage limit reached';
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Coupon usage limit reached';
    END IF;

    -- Check if user already redeemed this coupon
    SELECT id INTO v_existing_redemption
    FROM coupon_redemptions
    WHERE coupon_id = v_coupon_id AND user_id = p_user_id
    LIMIT 1;

    IF v_existing_redemption IS NOT NULL THEN
        SET p_message = 'You have already redeemed this coupon';
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'You have already redeemed this coupon';
    END IF;

    -- Create redemption
    INSERT INTO coupon_redemptions (coupon_id, user_id, expires_at, status)
    VALUES (
        v_coupon_id,
        p_user_id,
        CASE
            WHEN v_coupon_type = 'free_forever' THEN NULL
            ELSE DATE_ADD(NOW(), INTERVAL v_duration_days DAY)
        END,
        'active'
    );

    -- Increment usage count
    UPDATE coupons SET current_uses = current_uses + 1 WHERE id = v_coupon_id;

    -- Apply benefit based on type
    IF v_coupon_type = 'free_forever' THEN
        -- Mark user as comped
        UPDATE portal_users
        SET subscription_override = 'comp',
            subscription_override_until = NULL
        WHERE id = p_user_id;
    ELSEIF v_coupon_type = 'free_trial' THEN
        -- Extend trial period
        UPDATE portal_users
        SET subscription_override = 'extended',
            subscription_override_until = DATE_ADD(NOW(), INTERVAL v_duration_days DAY)
        WHERE id = p_user_id;
    END IF;
    -- For 'discount' type, the discount is applied at Stripe checkout

    SET p_success = 1;
    SET p_message = 'Coupon redeemed successfully';

END //

DELIMITER ;
