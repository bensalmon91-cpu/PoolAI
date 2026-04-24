<?php
/**
 * PoolAIssistant Admin - Client Management
 *
 * Provides methods for managing portal clients including:
 * - Listing clients with filters
 * - Getting client details
 * - Suspending/activating accounts
 * - Viewing client device data
 */

require_once __DIR__ . '/../config/database.php';

class AdminClients {
    private $pdo;

    public function __construct() {
        $this->pdo = db();
    }

    /**
     * List all clients with optional filters and pagination
     */
    public function listClients($options = []) {
        $page = max(1, intval($options['page'] ?? 1));
        $perPage = min(100, max(10, intval($options['per_page'] ?? 25)));
        $search = trim($options['search'] ?? '');
        $status = $options['status'] ?? null;
        $sortBy = $options['sort_by'] ?? 'created_at';
        $sortDir = strtoupper($options['sort_dir'] ?? 'DESC') === 'ASC' ? 'ASC' : 'DESC';

        // Build WHERE clause
        $where = ['1=1'];
        $params = [];

        if ($search) {
            $where[] = "(u.email LIKE ? OR u.name LIKE ? OR u.company LIKE ?)";
            $searchParam = "%$search%";
            $params[] = $searchParam;
            $params[] = $searchParam;
            $params[] = $searchParam;
        }

        if ($status && in_array($status, ['active', 'suspended', 'pending'])) {
            $where[] = "u.status = ?";
            $params[] = $status;
        }

        $whereClause = implode(' AND ', $where);

        // Validate sort column
        $allowedSorts = ['email', 'name', 'company', 'created_at', 'last_login_at', 'status', 'device_count'];
        if (!in_array($sortBy, $allowedSorts)) {
            $sortBy = 'created_at';
        }

        // Get total count
        $countSql = "
            SELECT COUNT(*) as total
            FROM portal_users u
            WHERE $whereClause
        ";
        $stmt = $this->pdo->prepare($countSql);
        $stmt->execute($params);
        $total = $stmt->fetch()['total'];

        // Get clients.
        // $sortBy is already whitelisted above; interpolate directly to avoid
        // the 1267 collation mismatch that bound params triggered against
        // portal_users' utf8mb4_general_ci columns.
        $orderColumn = $sortBy === 'device_count' ? 'device_count' : "u.$sortBy";
        $offset = ($page - 1) * $perPage;
        $sql = "
            SELECT
                u.id,
                u.email,
                u.name,
                u.company,
                u.phone,
                u.status,
                u.email_verified,
                u.created_at,
                u.last_login_at,
                u.subscription_override,
                u.subscription_override_until,
                u.suspended_at,
                u.suspended_reason,
                (SELECT COUNT(*) FROM user_devices ud WHERE ud.user_id = u.id) as device_count,
                s.status as subscription_status,
                p.name as plan_name,
                s.current_period_end
            FROM portal_users u
            LEFT JOIN user_subscriptions s ON s.user_id = u.id
            LEFT JOIN subscription_plans p ON p.id = s.plan_id
            WHERE $whereClause
            ORDER BY $orderColumn $sortDir
            LIMIT ? OFFSET ?
        ";

        $params[] = $perPage;
        $params[] = $offset;

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);
        $clients = $stmt->fetchAll();

        return [
            'clients' => $clients,
            'total' => $total,
            'page' => $page,
            'per_page' => $perPage,
            'total_pages' => ceil($total / $perPage),
        ];
    }

    /**
     * Get detailed client information
     */
    public function getClient($userId) {
        $stmt = $this->pdo->prepare("
            SELECT
                u.*,
                s.id as subscription_id,
                s.status as subscription_status,
                s.billing_interval,
                s.current_period_start,
                s.current_period_end,
                s.trial_end,
                s.cancel_at_period_end,
                s.cancelled_at,
                s.stripe_customer_id,
                p.name as plan_name,
                p.slug as plan_slug,
                p.price_monthly,
                p.price_yearly
            FROM portal_users u
            LEFT JOIN user_subscriptions s ON s.user_id = u.id
            LEFT JOIN subscription_plans p ON p.id = s.plan_id
            WHERE u.id = ?
        ");
        $stmt->execute([$userId]);
        return $stmt->fetch();
    }

    /**
     * Get devices linked to a client
     */
    public function getClientDevices($userId) {
        $stmt = $this->pdo->prepare("
            SELECT
                ud.id as link_id,
                ud.nickname,
                ud.role,
                ud.linked_at,
                d.id as device_id,
                d.device_uuid,
                d.name as alias,
                d.last_seen,
                d.is_active,
                h.software_version,
                h.ip_address,
                h.cpu_temp,
                h.memory_used_pct,
                h.disk_used_pct,
                h.uptime_seconds,
                h.alarms_total,
                h.alarms_critical,
                h.has_issues,
                CASE
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 20 MINUTE) THEN 'online'
                    WHEN d.last_seen > DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 'away'
                    ELSE 'offline'
                END as status
            FROM user_devices ud
            JOIN pi_devices d ON ud.device_id = d.id
            LEFT JOIN (
                SELECT h1.*
                FROM device_health h1
                INNER JOIN (
                    SELECT device_id, MAX(ts) as max_ts
                    FROM device_health
                    GROUP BY device_id
                ) h2 ON h1.device_id = h2.device_id AND h1.ts = h2.max_ts
            ) h ON h.device_id = d.id
            WHERE ud.user_id = ?
            ORDER BY ud.linked_at DESC
        ");
        $stmt->execute([$userId]);
        return $stmt->fetchAll();
    }

    /**
     * Get payment history for a client
     */
    public function getClientPayments($userId, $limit = 20) {
        $stmt = $this->pdo->prepare("
            SELECT
                id,
                amount,
                currency,
                status,
                description,
                failure_reason,
                receipt_url,
                invoice_pdf_url,
                created_at
            FROM payment_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ");
        $stmt->execute([$userId, $limit]);
        return $stmt->fetchAll();
    }

    /**
     * Get audit log for a client
     */
    public function getClientAuditLog($userId, $limit = 50) {
        $stmt = $this->pdo->prepare("
            SELECT
                action,
                details_json,
                ip_address,
                created_at
            FROM portal_audit_log
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ");
        $stmt->execute([$userId, $limit]);
        return $stmt->fetchAll();
    }

    /**
     * Get coupon redemptions for a client
     */
    public function getClientCoupons($userId) {
        $stmt = $this->pdo->prepare("
            SELECT
                r.id as redemption_id,
                r.redeemed_at,
                r.expires_at,
                r.status,
                c.code,
                c.type,
                c.discount_percent,
                c.notes
            FROM coupon_redemptions r
            JOIN coupons c ON c.id = r.coupon_id
            WHERE r.user_id = ?
            ORDER BY r.redeemed_at DESC
        ");
        $stmt->execute([$userId]);
        return $stmt->fetchAll();
    }

    /**
     * Suspend a client account
     */
    public function suspendClient($userId, $reason = '', $adminId = null) {
        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET status = 'suspended',
                suspended_at = NOW(),
                suspended_reason = ?,
                suspended_by = ?
            WHERE id = ?
        ");
        $stmt->execute([$reason, $adminId, $userId]);

        // Log the action
        $this->logAction($userId, 'account_suspended', [
            'reason' => $reason,
            'admin_id' => $adminId,
        ]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Activate a suspended client account
     */
    public function activateClient($userId, $adminId = null) {
        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET status = 'active',
                suspended_at = NULL,
                suspended_reason = NULL,
                suspended_by = NULL
            WHERE id = ?
        ");
        $stmt->execute([$userId]);

        // Log the action
        $this->logAction($userId, 'account_activated', [
            'admin_id' => $adminId,
        ]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Grant free access (comp account)
     */
    public function compAccount($userId, $reason = '', $adminId = null) {
        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET subscription_override = 'comp',
                subscription_override_until = NULL
            WHERE id = ?
        ");
        $stmt->execute([$userId]);

        // Log the action
        $this->logAction($userId, 'account_comped', [
            'reason' => $reason,
            'admin_id' => $adminId,
        ]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Extend trial period
     */
    public function extendTrial($userId, $days, $adminId = null) {
        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET subscription_override = 'extended',
                subscription_override_until = DATE_ADD(
                    COALESCE(subscription_override_until, NOW()),
                    INTERVAL ? DAY
                )
            WHERE id = ?
        ");
        $stmt->execute([$days, $userId]);

        // Log the action
        $this->logAction($userId, 'trial_extended', [
            'days' => $days,
            'admin_id' => $adminId,
        ]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Remove subscription override
     */
    public function removeOverride($userId, $adminId = null) {
        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET subscription_override = 'none',
                subscription_override_until = NULL
            WHERE id = ?
        ");
        $stmt->execute([$userId]);

        // Log the action
        $this->logAction($userId, 'override_removed', [
            'admin_id' => $adminId,
        ]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Delete a client account
     */
    public function deleteClient($userId, $adminId = null) {
        // Get client info for logging
        $client = $this->getClient($userId);
        if (!$client) {
            return false;
        }

        // Log before deletion
        $this->logAction(null, 'client_deleted', [
            'deleted_user_id' => $userId,
            'email' => $client['email'],
            'name' => $client['name'],
            'admin_id' => $adminId,
        ]);

        // Delete (cascades to related tables due to foreign keys)
        $stmt = $this->pdo->prepare("DELETE FROM portal_users WHERE id = ?");
        $stmt->execute([$userId]);

        return $stmt->rowCount() > 0;
    }

    /**
     * Get statistics summary
     */
    public function getStats() {
        $stats = [];

        // Total clients
        $stmt = $this->pdo->query("SELECT COUNT(*) as total FROM portal_users");
        $stats['total_clients'] = $stmt->fetch()['total'];

        // Active clients
        $stmt = $this->pdo->query("SELECT COUNT(*) as total FROM portal_users WHERE status = 'active'");
        $stats['active_clients'] = $stmt->fetch()['total'];

        // Suspended clients
        $stmt = $this->pdo->query("SELECT COUNT(*) as total FROM portal_users WHERE status = 'suspended'");
        $stats['suspended_clients'] = $stmt->fetch()['total'];

        // Clients with active subscriptions
        $stmt = $this->pdo->query("
            SELECT COUNT(DISTINCT user_id) as total
            FROM user_subscriptions
            WHERE status IN ('active', 'trialing')
        ");
        $stats['subscribed_clients'] = $stmt->fetch()['total'];

        // Comped accounts
        $stmt = $this->pdo->query("SELECT COUNT(*) as total FROM portal_users WHERE subscription_override = 'comp'");
        $stats['comped_clients'] = $stmt->fetch()['total'];

        // Total linked devices
        $stmt = $this->pdo->query("SELECT COUNT(*) as total FROM user_devices");
        $stats['total_linked_devices'] = $stmt->fetch()['total'];

        // New clients this month
        $stmt = $this->pdo->query("
            SELECT COUNT(*) as total FROM portal_users
            WHERE created_at >= DATE_FORMAT(NOW(), '%Y-%m-01')
        ");
        $stats['new_this_month'] = $stmt->fetch()['total'];

        return $stats;
    }

    /**
     * Log an admin action
     */
    private function logAction($userId, $action, $details = []) {
        $stmt = $this->pdo->prepare("
            INSERT INTO portal_audit_log (user_id, action, details_json, ip_address, created_at)
            VALUES (?, ?, ?, ?, NOW())
        ");
        $stmt->execute([
            $userId,
            $action,
            json_encode($details),
            $_SERVER['REMOTE_ADDR'] ?? null,
        ]);
    }

    /**
     * Impersonate a client (generate a temporary session)
     */
    public function generateImpersonationToken($userId, $adminId) {
        $token = bin2hex(random_bytes(32));
        $expires = date('Y-m-d H:i:s', strtotime('+1 hour'));

        $stmt = $this->pdo->prepare("
            INSERT INTO portal_sessions (id, user_id, ip_address, user_agent, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ");
        $stmt->execute([
            $token,
            $userId,
            $_SERVER['REMOTE_ADDR'] ?? null,
            'Admin Impersonation (admin_id=' . $adminId . ')',
            $expires,
        ]);

        // Log the action
        $this->logAction($userId, 'admin_impersonation', [
            'admin_id' => $adminId,
            'session_expires' => $expires,
        ]);

        return $token;
    }
}
