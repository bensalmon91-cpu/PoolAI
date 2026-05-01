<?php
/**
 * Read-only projection over the `v_user_subscription_status` view (defined in
 * `database/schema_billing.sql`). The view computes `access_status` (active /
 * grace / inactive) from `user_subscriptions`, `subscription_plans`, and the
 * `subscription_override` flags on `portal_users`. Mutating methods live
 * elsewhere.
 */

require_once __DIR__ . '/../config/database.php';

class Subscription {

    /**
     * Status snapshot for a user.
     *
     * Returns:
     *   access_status    string  'active' | 'grace' | 'inactive' | 'no_subscription'
     *   plan_name        ?string Stripe-side plan label, or null on free trial
     *   plan_slug        ?string
     *   status           ?string raw subscription_status (trialing/active/past_due/canceled)
     *   current_period_end ?string DATETIME
     *   trial_end        ?string DATETIME
     *   days_remaining   ?int   integer days until current_period_end / trial_end (whichever is sooner & in future)
     *   override         ?string 'comp' / 'extended' / null
     *   override_until   ?string DATETIME
     */
    public static function getStatus(int $userId): array {
        $stmt = db()->prepare("
            SELECT
                subscription_id,
                plan_name,
                plan_slug,
                subscription_status,
                current_period_end,
                trial_end,
                cancel_at_period_end,
                subscription_override,
                subscription_override_until,
                access_status
            FROM v_user_subscription_status
            WHERE user_id = ?
            LIMIT 1
        ");
        $stmt->execute([$userId]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$row) {
            // User row missing entirely (shouldn't happen post-login) — treat as no sub.
            return self::emptyStatus();
        }

        // No subscription row — view still returns the user, just with NULLs.
        $hasSub = $row['subscription_id'] !== null;
        $accessStatus = $hasSub ? $row['access_status'] : 'no_subscription';

        // Days remaining — pick the soonest future end-date that's relevant.
        $daysRemaining = null;
        $endDate = self::primaryEndDate($row);
        if ($endDate) {
            $diff = strtotime($endDate) - time();
            $daysRemaining = $diff > 0 ? (int)ceil($diff / 86400) : 0;
        }

        return [
            'access_status'        => $accessStatus,
            'plan_name'            => $row['plan_name'],
            'plan_slug'            => $row['plan_slug'],
            'status'               => $row['subscription_status'],
            'current_period_end'   => $row['current_period_end'],
            'trial_end'            => $row['trial_end'],
            'cancel_at_period_end' => (bool)($row['cancel_at_period_end'] ?? false),
            'override'             => $row['subscription_override'],
            'override_until'       => $row['subscription_override_until'],
            'days_remaining'       => $daysRemaining,
        ];
    }

    private static function primaryEndDate(array $row): ?string {
        // Trialing rows MUST use trial_end. Falling through to current_period_end
        // or override_until would silently render an unrelated date (e.g. an old
        // comp coupon's expiry) as the trial deadline.
        $status = $row['subscription_status'] ?? null;
        if ($status === 'trialing') {
            if (!empty($row['trial_end'])) {
                return $row['trial_end'];
            }
            error_log(sprintf(
                "Subscription: trialing subscription #%s has no trial_end",
                $row['subscription_id'] ?? '?'
            ));
            return null;
        }
        if (!empty($row['current_period_end'])) {
            return $row['current_period_end'];
        }
        if (!empty($row['subscription_override_until'])) {
            return $row['subscription_override_until'];
        }
        return $row['trial_end'] ?: null;
    }

    private static function emptyStatus(): array {
        return [
            'access_status'        => 'no_subscription',
            'plan_name'            => null,
            'plan_slug'            => null,
            'status'               => null,
            'current_period_end'   => null,
            'trial_end'            => null,
            'cancel_at_period_end' => false,
            'override'             => null,
            'override_until'       => null,
            'days_remaining'       => null,
        ];
    }
}
