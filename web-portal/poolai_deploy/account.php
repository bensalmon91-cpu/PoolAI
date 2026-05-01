<?php
/**
 * PoolAIssistant Portal - Account Settings
 */

require_once __DIR__ . '/includes/PortalAuth.php';
require_once __DIR__ . '/includes/Subscription.php';
require_once __DIR__ . '/config/database.php';

$auth = new PortalAuth();
$auth->requireAuth();

$user = $auth->getUser();
$error = '';
$success = '';

// Handle form submissions
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $csrf = $_POST['csrf_token'] ?? '';

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
    } else {
        $action = $_POST['action'] ?? '';
        $pdo = db();

        switch ($action) {
            case 'update_profile':
                $name = trim($_POST['name'] ?? '');
                $company = trim($_POST['company'] ?? '');

                $stmt = $pdo->prepare("UPDATE portal_users SET name = ?, company = ? WHERE id = ?");
                $stmt->execute([$name, $company, $user['id']]);

                // Refresh user data
                $_SESSION['portal_user_name'] = $name;
                $success = 'Profile updated successfully.';

                // Reload user data
                $stmt = $pdo->prepare("SELECT * FROM portal_users WHERE id = ?");
                $stmt->execute([$user['id']]);
                $user = $stmt->fetch(PDO::FETCH_ASSOC);
                break;

            case 'change_password':
                $currentPassword = $_POST['current_password'] ?? '';
                $newPassword = $_POST['new_password'] ?? '';
                $confirmPassword = $_POST['confirm_password'] ?? '';

                // Verify current password
                $stmt = $pdo->prepare("SELECT password_hash FROM portal_users WHERE id = ?");
                $stmt->execute([$user['id']]);
                $row = $stmt->fetch(PDO::FETCH_ASSOC);

                if (!password_verify($currentPassword, $row['password_hash'])) {
                    $error = 'Current password is incorrect.';
                } elseif ($newPassword !== $confirmPassword) {
                    $error = 'New passwords do not match.';
                } elseif (strlen($newPassword) < PORTAL_PASSWORD_MIN_LENGTH) {
                    $error = 'Password must be at least ' . PORTAL_PASSWORD_MIN_LENGTH . ' characters.';
                } else {
                    $newHash = password_hash($newPassword, PASSWORD_BCRYPT, ['cost' => PORTAL_PASSWORD_BCRYPT_COST]);
                    $stmt = $pdo->prepare("UPDATE portal_users SET password_hash = ? WHERE id = ?");
                    $stmt->execute([$newHash, $user['id']]);
                    $success = 'Password changed successfully.';
                }
                break;
        }
    }
}

$csrfToken = $auth->generateCSRFToken();
$subscription = Subscription::getStatus((int)$user['id']);

/**
 * Map access_status → (badge label, badge css colour, primary message).
 * Phase D will replace the disabled buttons with real Stripe Checkout links.
 */
function sub_view(array $s): array {
    $days = $s['days_remaining'];
    $plan = $s['plan_name'] ?: 'Free trial';

    switch ($s['access_status']) {
        case 'active':
            if ($s['status'] === 'trialing') {
                return ['Trial', 'success', $plan, $days !== null ? "Trial ends in $days days" : 'Trial active'];
            }
            if ($s['override'] === 'comp') {
                return ['Comped', 'success', $plan, 'Complimentary access'];
            }
            $when = $s['current_period_end'] ? date('d M Y', strtotime($s['current_period_end'])) : null;
            return ['Active', 'success', $plan, $when ? "Renews $when" : 'Subscription active'];
        case 'grace':
            return ['Past due', 'warning', $plan, $days !== null ? "Grace period — $days days remaining" : 'Payment overdue — please update billing'];
        case 'inactive':
            return ['Inactive', 'danger', $plan, 'No active subscription'];
        case 'no_subscription':
        default:
            return ['No plan', '', 'No subscription', 'Start a free trial to access cloud features'];
    }
}
[$subBadge, $subBadgeCls, $subPlan, $subMsg] = sub_view($subscription);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Account Settings - PoolAIssistant</title>

    <!-- PWA Meta Tags -->
    <meta name="theme-color" content="#0066cc">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">

    <link rel="stylesheet" href="assets/css/portal.css">
    <script src="/assets/js/pwa.js" defer></script>
    <style>
        .settings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
        }
        .settings-card {
            background: var(--card-bg);
            border-radius: var(--border-radius-lg);
            box-shadow: var(--shadow-sm);
            padding: 1.5rem;
        }
        .settings-card h3 {
            margin-bottom: 1.5rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--border-color);
        }
        .account-info {
            margin-bottom: 2rem;
        }
        .account-info-item {
            display: flex;
            justify-content: space-between;
            padding: 0.75rem 0;
            border-bottom: 1px solid var(--border-color);
        }
        .account-info-item:last-child {
            border-bottom: none;
        }
        .account-info-label {
            color: var(--text-muted);
        }
        .back-link {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
            color: var(--text-muted);
        }
        .back-link:hover {
            color: var(--primary-color);
        }
        @media (max-width: 768px) {
            .settings-grid {
                grid-template-columns: 1fr;
            }
        }
        .sub-card {
            background: var(--card-bg);
            border-radius: var(--border-radius-lg);
            box-shadow: var(--shadow-sm);
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .sub-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--border-color);
        }
        .sub-header h3 { margin: 0; }
        .sub-badge {
            display: inline-block;
            padding: 0.25rem 0.625rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            background: var(--gray-200);
            color: var(--text-muted);
        }
        .sub-badge.success { background: rgba(34,197,94,0.15);  color: #15803d; }
        .sub-badge.warning { background: rgba(245,158,11,0.15); color: #b45309; }
        .sub-badge.danger  { background: rgba(239,68,68,0.15);  color: #b91c1c; }
        .sub-plan { font-size: 1.125rem; font-weight: 500; margin-bottom: 0.25rem; }
        .sub-msg  { color: var(--text-muted); margin-bottom: 1rem; }
        .sub-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .sub-actions .btn[disabled] {
            opacity: 0.55;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-brand">
            <h1>PoolAIssistant</h1>
        </div>
        <div class="nav-user">
            <span><?= htmlspecialchars($user['name'] ?: $user['email']) ?></span>
            <a href="account.php" class="nav-link">Account</a>
            <a href="logout.php" class="nav-link">Logout</a>
        </div>
    </nav>

    <main class="dashboard-container">
        <a href="dashboard.php" class="back-link">&larr; Back to Dashboard</a>

        <h2>Account Settings</h2>

        <?php if ($error): ?>
            <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <?php if ($success): ?>
            <div class="alert alert-success"><?= htmlspecialchars($success) ?></div>
        <?php endif; ?>

        <div class="account-info">
            <div class="account-info-item">
                <span class="account-info-label">Email</span>
                <span><?= htmlspecialchars($user['email']) ?></span>
            </div>
            <div class="account-info-item">
                <span class="account-info-label">Member Since</span>
                <span><?= date('d M Y', strtotime($user['created_at'])) ?></span>
            </div>
            <?php if ($user['last_login_at']): ?>
                <div class="account-info-item">
                    <span class="account-info-label">Last Login</span>
                    <span><?= date('d M Y H:i', strtotime($user['last_login_at'])) ?></span>
                </div>
            <?php endif; ?>
        </div>

        <div class="sub-card">
            <div class="sub-header">
                <h3>Subscription</h3>
                <span class="sub-badge <?= htmlspecialchars($subBadgeCls) ?>"><?= htmlspecialchars($subBadge) ?></span>
            </div>
            <div class="sub-plan"><?= htmlspecialchars($subPlan) ?></div>
            <div class="sub-msg"><?= htmlspecialchars($subMsg) ?></div>
            <div class="sub-actions">
                <button type="button" class="btn btn-primary" disabled
                        title="Coming soon — Stripe checkout is in the next release">
                    <?= $subscription['access_status'] === 'no_subscription' ? 'Subscribe' : 'Manage Subscription' ?>
                </button>
                <button type="button" class="btn" disabled
                        title="Coming soon — coupon redemption ships with billing">
                    Redeem Coupon
                </button>
            </div>
        </div>

        <div class="settings-grid">
            <div class="settings-card">
                <h3>Profile Information</h3>
                <form method="POST">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">
                    <input type="hidden" name="action" value="update_profile">

                    <div class="form-group">
                        <label for="name">Full Name</label>
                        <input type="text" id="name" name="name"
                               value="<?= htmlspecialchars($user['name'] ?? '') ?>">
                    </div>

                    <div class="form-group">
                        <label for="company">Company / Organisation</label>
                        <input type="text" id="company" name="company"
                               value="<?= htmlspecialchars($user['company'] ?? '') ?>">
                    </div>

                    <button type="submit" class="btn btn-primary">Save Changes</button>
                </form>
            </div>

            <div class="settings-card">
                <h3>Change Password</h3>
                <form method="POST">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">
                    <input type="hidden" name="action" value="change_password">

                    <div class="form-group">
                        <label for="current_password">Current Password</label>
                        <input type="password" id="current_password" name="current_password" required>
                    </div>

                    <div class="form-group">
                        <label for="new_password">New Password</label>
                        <input type="password" id="new_password" name="new_password" required
                               minlength="<?= PORTAL_PASSWORD_MIN_LENGTH ?>">
                        <small>Minimum <?= PORTAL_PASSWORD_MIN_LENGTH ?> characters</small>
                    </div>

                    <div class="form-group">
                        <label for="confirm_password">Confirm New Password</label>
                        <input type="password" id="confirm_password" name="confirm_password" required>
                    </div>

                    <button type="submit" class="btn btn-primary">Change Password</button>
                </form>
            </div>
        </div>
    </main>
</body>
</html>
