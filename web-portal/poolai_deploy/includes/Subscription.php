<?php
/**
 * Read-only projection over the `v_user_subscription_status` view (defined in
 * `database/schema_billing.sql`). The view computes `access_status` (active /
 * grace / inactive) from `user_subscriptions`, `subscription_plans`, and the
 * `subscription_override` flags on `portal_users`. Mutating methods live
 * elsewhere.
 */

require_once __DIR__ . '/../config/database.php';

/**
 * Closed set of access states the rest of the codebase branches on. Backed by
 * the same string values the SQL view returns so casting via tryFrom() is
 * direct. Anything outside this set means a typo or a view-side rename — both
 * cases we want to fail loudly rather than silently fall through.
 */
enum AccessStatus: string {
    case Active         = 'active';
    case Grace          = 'grace';
    case Inactive       = 'inactive';
    case NoSubscription = 'no_subscription';
}

class Subscription {

    /**
     * Status snapshot for a user.
     *
     * Returns:
     *   access_status    string  one of AccessStatus::*->value
     *   plan_name        ?string Stripe-side plan label, or null on free trial
     *   plan_slug        ?string
     *   status           ?string raw subscription_status (trialing/active/past_due/canceled)
     *   current_period_end ?string DATETIME
     *   trial_end        ?string DATETIME
     *   cancel_at_period_end bool
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
        $accessStatus = $hasSub
            ? ($row['access_status'] ?? AccessStatus::Inactive->value)
            : AccessStatus::NoSubscription->value;

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

    /**
     * Project the status array onto the four UI fields the subscription card
     * needs: badge label, badge css class, plan name, primary message line.
     *
     * Lives here (not on each consumer page) so when billing.php and
     * redeem.php arrive in Phase D, they reuse the same translation rather
     * than copy-pasting the switch.
     *
     * Returns: ['badge', 'badgeCls', 'plan', 'msg']
     */
    public static function viewModel(array $s): array {
        $days = $s['days_remaining'] ?? null;
        $plan = $s['plan_name'] ?: 'Free trial';
        $access = AccessStatus::tryFrom($s['access_status'] ?? '');

        $badge = $badgeCls = $msg = '';

        switch ($access) {
            case AccessStatus::Active:
                if ($s['status'] === 'trialing') {
                    $badge = 'Trial'; $badgeCls = 'success';
                    $msg = $days !== null ? "Trial ends in $days days" : 'Trial active';
                } elseif (!empty($s['cancel_at_period_end']) && !empty($s['current_period_end'])) {
                    // Canceled-but-still-active: subscription is paid through
                    // current_period_end and won't renew. "Renews" is misleading.
                    $when = date('d M Y', strtotime($s['current_period_end']));
                    $badge = 'Ending'; $badgeCls = 'warning';
                    $msg = "Cancels on $when";
                } elseif ($s['override'] === 'comp') {
                    $badge = 'Comped'; $badgeCls = 'success';
                    $msg = 'Complimentary access';
                } else {
                    $when = !empty($s['current_period_end'])
                        ? date('d M Y', strtotime($s['current_period_end']))
                        : null;
                    $badge = 'Active'; $badgeCls = 'success';
                    $msg = $when ? "Renews $when" : 'Subscription active';
                }
                break;

            case AccessStatus::Grace:
                $badge = 'Past due'; $badgeCls = 'warning';
                $msg = $days !== null
                    ? "Grace period — $days days remaining"
                    : 'Payment overdue — please update billing';
                break;

            case AccessStatus::Inactive:
                $badge = 'Inactive'; $badgeCls = 'danger';
                $msg = 'No active subscription';
                break;

            case AccessStatus::NoSubscription:
                $badge = 'No plan'; $badgeCls = '';
                $plan = 'No subscription';
                $msg  = 'Start a free trial to access cloud features';
                break;

            case null:
                // Unknown access_status — surface the data-integrity issue
                // instead of silently aliasing to 'no_subscription'.
                error_log(sprintf(
                    "Subscription::viewModel: unknown access_status %s",
                    var_export($s['access_status'] ?? null, true)
                ));
                $badge = 'Unknown'; $badgeCls = 'danger';
                $msg = 'Subscription status unavailable — please contact support';
                break;
        }

        return ['badge' => $badge, 'badgeCls' => $badgeCls, 'plan' => $plan, 'msg' => $msg];
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
            'access_status'        => AccessStatus::NoSubscription->value,
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
