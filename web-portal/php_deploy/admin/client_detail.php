<?php
/**
 * PoolAIssistant Admin Panel - Client Detail View
 * Shows detailed information about a single client
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AdminClients.php';

// Require admin login
requireAdmin();

$adminClients = new AdminClients();

$clientId = intval($_GET['id'] ?? 0);
if (!$clientId) {
    header('Location: clients.php');
    exit;
}

$client = $adminClients->getClient($clientId);
if (!$client) {
    header('Location: clients.php');
    exit;
}

$devices = $adminClients->getClientDevices($clientId);
$payments = $adminClients->getClientPayments($clientId);
$coupons = $adminClients->getClientCoupons($clientId);
$auditLog = $adminClients->getClientAuditLog($clientId, 20);

// Handle actions via POST
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';
    $result = ['ok' => false, 'error' => 'Unknown action'];

    switch ($action) {
        case 'suspend':
            $reason = trim($_POST['reason'] ?? '');
            if ($adminClients->suspendClient($clientId, $reason)) {
                $result = ['ok' => true];
            }
            break;

        case 'activate':
            if ($adminClients->activateClient($clientId)) {
                $result = ['ok' => true];
            }
            break;

        case 'comp':
            $reason = trim($_POST['reason'] ?? '');
            if ($adminClients->compAccount($clientId, $reason)) {
                $result = ['ok' => true];
            }
            break;

        case 'extend_trial':
            $days = intval($_POST['days'] ?? 30);
            if ($adminClients->extendTrial($clientId, $days)) {
                $result = ['ok' => true];
            }
            break;

        case 'remove_override':
            if ($adminClients->removeOverride($clientId)) {
                $result = ['ok' => true];
            }
            break;

        case 'delete':
            if ($adminClients->deleteClient($clientId)) {
                header('Location: clients.php?deleted=1');
                exit;
            }
            break;
    }

    if ($result['ok']) {
        header('Location: client_detail.php?id=' . $clientId . '&updated=1');
        exit;
    }
}

// Helper function
function formatBytes($bytes) {
    if ($bytes < 1024) return $bytes . ' B';
    if ($bytes < 1048576) return round($bytes / 1024, 1) . ' KB';
    return round($bytes / 1048576, 1) . ' MB';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($client['name'] ?: $client['email']) ?> - PoolAIssistant Admin</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-2: #334155;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #475569;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }

        .back-link {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--text-muted);
            text-decoration: none;
            margin-bottom: 20px;
        }
        .back-link:hover { color: var(--text); }

        .client-header {
            background: var(--surface);
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
        }
        .client-header h1 { font-size: 1.5rem; margin-bottom: 4px; }
        .client-header .email { color: var(--text-muted); font-size: 0.875rem; }
        .client-header .meta { margin-top: 12px; font-size: 0.875rem; color: var(--text-muted); }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge.active { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge.suspended { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .badge.pending { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge.comp { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }
        .badge.trialing { background: rgba(59, 130, 246, 0.2); color: var(--accent); }
        .badge.online { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge.offline { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .badge.away { background: rgba(245, 158, 11, 0.2); color: var(--warning); }

        .actions-bar {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .btn {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.875rem;
            cursor: pointer;
            border: none;
            text-decoration: none;
            transition: all 0.15s;
        }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-secondary { background: var(--surface-2); color: var(--text); }
        .btn-secondary:hover { background: var(--border); }
        .btn-danger { background: var(--danger); color: white; }
        .btn-warning { background: var(--warning); color: #000; }
        .btn-success { background: var(--success); color: white; }
        .btn-purple { background: #8b5cf6; color: white; }
        .btn-sm { padding: 4px 10px; font-size: 0.75rem; }

        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 24px; }

        .card {
            background: var(--surface);
            border-radius: 12px;
            padding: 20px;
        }
        .card h2 {
            font-size: 1rem;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--surface-2);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card h2::before {
            content: '';
            width: 4px;
            height: 20px;
            background: var(--accent);
            border-radius: 2px;
        }

        .info-grid {
            display: grid;
            grid-template-columns: 120px 1fr;
            gap: 8px 16px;
            font-size: 0.875rem;
        }
        .info-grid .label { color: var(--text-muted); }
        .info-grid .value { font-weight: 500; }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }
        th, td { padding: 10px 12px; text-align: left; }
        th { color: var(--text-muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
        tr:not(:last-child) td { border-bottom: 1px solid var(--surface-2); }

        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.875rem; }
        .mono { font-family: 'SF Mono', Monaco, monospace; font-size: 0.8rem; }

        .empty { color: var(--text-muted); text-align: center; padding: 24px; }

        .alert {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 0.875rem;
        }
        .alert.success { background: rgba(34, 197, 94, 0.1); border: 1px solid var(--success); color: var(--success); }
        .alert.warning { background: rgba(245, 158, 11, 0.1); border: 1px solid var(--warning); color: var(--warning); }

        .device-card {
            background: var(--surface-2);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .device-card:last-child { margin-bottom: 0; }
        .device-info { flex: 1; }
        .device-name { font-weight: 500; }
        .device-meta { font-size: 0.75rem; color: var(--text-muted); }

        @media (max-width: 768px) {
            .container { padding: 12px; }
            .grid { grid-template-columns: 1fr; }
            .client-header { flex-direction: column; }
            .actions-bar { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="clients.php" class="back-link">&larr; Back to Clients</a>

        <?php if (isset($_GET['updated'])): ?>
        <div class="alert success">Client updated successfully.</div>
        <?php endif; ?>

        <?php if ($client['status'] === 'suspended'): ?>
        <div class="alert warning">
            This account is suspended.
            <?php if ($client['suspended_reason']): ?>
            Reason: <?= htmlspecialchars($client['suspended_reason']) ?>
            <?php endif; ?>
        </div>
        <?php endif; ?>

        <div class="client-header">
            <div>
                <h1><?= htmlspecialchars($client['name'] ?: 'Unnamed Client') ?></h1>
                <div class="email"><?= htmlspecialchars($client['email']) ?></div>
                <div class="meta">
                    <span class="badge <?= $client['status'] ?>"><?= ucfirst($client['status']) ?></span>
                    <?php if ($client['subscription_override'] === 'comp'): ?>
                    <span class="badge comp">Comped</span>
                    <?php elseif ($client['subscription_override'] === 'extended'): ?>
                    <span class="badge trialing">Extended Trial</span>
                    <?php endif; ?>
                    <?php if (!$client['email_verified']): ?>
                    <span class="badge pending">Email Unverified</span>
                    <?php endif; ?>
                    &bull;
                    Joined <?= date('M j, Y', strtotime($client['created_at'])) ?>
                    <?php if ($client['last_login_at']): ?>
                    &bull; Last login <?= date('M j, Y H:i', strtotime($client['last_login_at'])) ?>
                    <?php endif; ?>
                </div>
            </div>
            <div class="actions-bar">
                <?php if ($client['status'] === 'active'): ?>
                <form method="POST" style="display: inline;">
                    <input type="hidden" name="action" value="suspend">
                    <input type="hidden" name="reason" id="suspend-reason">
                    <button type="submit" class="btn btn-warning"
                            onclick="document.getElementById('suspend-reason').value = prompt('Reason for suspension:') || ''; return document.getElementById('suspend-reason').value !== null;">
                        Suspend
                    </button>
                </form>
                <?php else: ?>
                <form method="POST" style="display: inline;">
                    <input type="hidden" name="action" value="activate">
                    <button type="submit" class="btn btn-success">Activate</button>
                </form>
                <?php endif; ?>

                <?php if ($client['subscription_override'] !== 'comp'): ?>
                <form method="POST" style="display: inline;">
                    <input type="hidden" name="action" value="comp">
                    <button type="submit" class="btn btn-purple"
                            onclick="return confirm('Grant permanent free access to this account?');">
                        Comp Account
                    </button>
                </form>
                <?php else: ?>
                <form method="POST" style="display: inline;">
                    <input type="hidden" name="action" value="remove_override">
                    <button type="submit" class="btn btn-secondary"
                            onclick="return confirm('Remove comp status from this account?');">
                        Remove Comp
                    </button>
                </form>
                <?php endif; ?>

                <form method="POST" style="display: inline;">
                    <input type="hidden" name="action" value="extend_trial">
                    <input type="hidden" name="days" id="extend-days">
                    <button type="submit" class="btn btn-secondary"
                            onclick="var d = prompt('Extend trial by how many days?', '30'); if (!d) return false; document.getElementById('extend-days').value = d; return true;">
                        Extend Trial
                    </button>
                </form>

                <form method="POST" style="display: inline;">
                    <input type="hidden" name="action" value="delete">
                    <button type="submit" class="btn btn-danger btn-sm"
                            onclick="return confirm('DELETE this client account?\n\nThis cannot be undone!');">
                        Delete
                    </button>
                </form>
            </div>
        </div>

        <div class="grid">
            <!-- Account Info -->
            <div class="card">
                <h2>Account Information</h2>
                <div class="info-grid">
                    <span class="label">Name</span>
                    <span class="value"><?= htmlspecialchars($client['name'] ?: '-') ?></span>

                    <span class="label">Email</span>
                    <span class="value"><?= htmlspecialchars($client['email']) ?></span>

                    <span class="label">Company</span>
                    <span class="value"><?= htmlspecialchars($client['company'] ?: '-') ?></span>

                    <span class="label">Phone</span>
                    <span class="value"><?= htmlspecialchars($client['phone'] ?: '-') ?></span>

                    <span class="label">Created</span>
                    <span class="value"><?= date('M j, Y H:i', strtotime($client['created_at'])) ?></span>

                    <span class="label">Last Login</span>
                    <span class="value"><?= $client['last_login_at'] ? date('M j, Y H:i', strtotime($client['last_login_at'])) : 'Never' ?></span>
                </div>
            </div>

            <!-- Subscription -->
            <div class="card">
                <h2>Subscription</h2>
                <?php if ($client['subscription_override'] === 'comp'): ?>
                <div class="info-grid">
                    <span class="label">Status</span>
                    <span class="value"><span class="badge comp">Comped (Free Forever)</span></span>
                </div>
                <?php elseif ($client['subscription_override'] === 'extended'): ?>
                <div class="info-grid">
                    <span class="label">Status</span>
                    <span class="value"><span class="badge trialing">Extended Trial</span></span>

                    <span class="label">Expires</span>
                    <span class="value"><?= $client['subscription_override_until'] ? date('M j, Y', strtotime($client['subscription_override_until'])) : 'N/A' ?></span>
                </div>
                <?php elseif ($client['plan_name']): ?>
                <div class="info-grid">
                    <span class="label">Plan</span>
                    <span class="value"><?= htmlspecialchars($client['plan_name']) ?></span>

                    <span class="label">Status</span>
                    <span class="value"><span class="badge <?= $client['subscription_status'] ?>"><?= ucfirst($client['subscription_status'] ?? 'Unknown') ?></span></span>

                    <span class="label">Billing</span>
                    <span class="value"><?= ucfirst($client['billing_interval'] ?? 'monthly') ?></span>

                    <span class="label">Period End</span>
                    <span class="value"><?= $client['current_period_end'] ? date('M j, Y', strtotime($client['current_period_end'])) : '-' ?></span>

                    <?php if ($client['cancel_at_period_end']): ?>
                    <span class="label">Cancels At</span>
                    <span class="value text-muted"><?= date('M j, Y', strtotime($client['current_period_end'])) ?></span>
                    <?php endif; ?>
                </div>
                <?php else: ?>
                <p class="text-muted">No active subscription</p>
                <?php endif; ?>
            </div>
        </div>

        <!-- Devices -->
        <div class="card" style="margin-top: 24px;">
            <h2>Linked Devices (<?= count($devices) ?>)</h2>
            <?php if (empty($devices)): ?>
            <p class="empty">No devices linked to this account.</p>
            <?php else: ?>
            <?php foreach ($devices as $device): ?>
            <div class="device-card">
                <div class="device-info">
                    <div class="device-name">
                        <?= htmlspecialchars($device['nickname'] ?: $device['alias'] ?: 'Unnamed Device') ?>
                        <span class="badge <?= $device['status'] ?>"><?= ucfirst($device['status']) ?></span>
                    </div>
                    <div class="device-meta">
                        <?= htmlspecialchars($device['software_version'] ?? '-') ?> &bull;
                        <?= htmlspecialchars($device['ip_address'] ?? '-') ?> &bull;
                        Linked <?= date('M j, Y', strtotime($device['linked_at'])) ?>
                        <?php if ($device['alarms_total'] > 0): ?>
                        &bull; <span style="color: var(--warning);"><?= $device['alarms_total'] ?> alarm<?= $device['alarms_total'] > 1 ? 's' : '' ?></span>
                        <?php endif; ?>
                    </div>
                </div>
                <a href="../portal/device.php?id=<?= $device['device_id'] ?>" class="btn btn-sm btn-secondary" target="_blank">
                    View Data
                </a>
            </div>
            <?php endforeach; ?>
            <?php endif; ?>
        </div>

        <div class="grid" style="margin-top: 24px;">
            <!-- Payments -->
            <div class="card">
                <h2>Payment History</h2>
                <?php if (empty($payments)): ?>
                <p class="empty">No payment history.</p>
                <?php else: ?>
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Amount</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($payments as $payment): ?>
                        <tr>
                            <td><?= date('M j, Y', strtotime($payment['created_at'])) ?></td>
                            <td>&pound;<?= number_format($payment['amount'], 2) ?></td>
                            <td>
                                <span class="badge <?= $payment['status'] === 'succeeded' ? 'active' : ($payment['status'] === 'failed' ? 'suspended' : 'pending') ?>">
                                    <?= ucfirst($payment['status']) ?>
                                </span>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
                <?php endif; ?>
            </div>

            <!-- Coupons -->
            <div class="card">
                <h2>Coupon Redemptions</h2>
                <?php if (empty($coupons)): ?>
                <p class="empty">No coupons redeemed.</p>
                <?php else: ?>
                <table>
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Type</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($coupons as $coupon): ?>
                        <tr>
                            <td class="mono"><?= htmlspecialchars($coupon['code']) ?></td>
                            <td><?= htmlspecialchars($coupon['type']) ?></td>
                            <td>
                                <span class="badge <?= $coupon['status'] === 'active' ? 'active' : 'suspended' ?>">
                                    <?= ucfirst($coupon['status']) ?>
                                </span>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
                <?php endif; ?>
            </div>
        </div>

        <!-- Audit Log -->
        <div class="card" style="margin-top: 24px;">
            <h2>Activity Log</h2>
            <?php if (empty($auditLog)): ?>
            <p class="empty">No activity recorded.</p>
            <?php else: ?>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Action</th>
                        <th>Details</th>
                        <th>IP</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($auditLog as $log): ?>
                    <tr>
                        <td class="text-sm"><?= date('M j, H:i', strtotime($log['created_at'])) ?></td>
                        <td><?= htmlspecialchars($log['action']) ?></td>
                        <td class="text-sm text-muted">
                            <?php
                            $details = json_decode($log['details_json'], true);
                            if ($details) {
                                echo htmlspecialchars(substr(json_encode($details), 0, 100));
                            }
                            ?>
                        </td>
                        <td class="mono text-muted"><?= htmlspecialchars($log['ip_address'] ?? '-') ?></td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            <?php endif; ?>
        </div>
    </div>
</body>
</html>
