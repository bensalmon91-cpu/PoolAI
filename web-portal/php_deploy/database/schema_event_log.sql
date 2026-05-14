-- Unified event log for admin actions, portal events, and Pi-cloud communications.
-- Replaces portal_audit_log (which mixed portal auth events and admin
-- client-management actions, with no tier/result/target columns) and complements
-- the flat-file admin_audit.log (which captures HTTP-level URL/status only).
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS event_log (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tier            ENUM('admin','portal','device','system') NOT NULL,
    actor_type      ENUM('admin','user','device','system','anonymous') NOT NULL,
    actor_id        VARCHAR(64) NULL,
    action          VARCHAR(64) NOT NULL,
    target_type     VARCHAR(32) NULL,
    target_id       VARCHAR(64) NULL,
    result          ENUM('ok','fail','denied') NOT NULL DEFAULT 'ok',
    details_json    JSON NULL,
    ip_address      VARCHAR(45) NULL,
    user_agent      VARCHAR(255) NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created (created_at),
    INDEX idx_tier_action (tier, action, created_at),
    INDEX idx_actor (actor_type, actor_id, created_at),
    INDEX idx_target (target_type, target_id, created_at),
    INDEX idx_result (result, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
