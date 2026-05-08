<?php
/**
 * Admin Setup Script
 * Creates admin user and runs migrations
 *
 * IMPORTANT: Delete this file after setup!
 */

require_once __DIR__ . '/../config/database.php';

$message = '';
$error = '';

// Process form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';

    if ($action === 'create_admin') {
        $username = trim($_POST['username'] ?? '');
        $password = $_POST['password'] ?? '';
        $confirm = $_POST['confirm'] ?? '';

        if (empty($username) || empty($password)) {
            $error = 'Username and password required';
        } elseif ($password !== $confirm) {
            $error = 'Passwords do not match';
        } elseif (strlen($password) < 8) {
            $error = 'Password must be at least 8 characters';
        } else {
            try {
                $pdo = db();

                // Create admin_users table if not exists
                $pdo->exec("
                    CREATE TABLE IF NOT EXISTS admin_users (
                        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(50) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                ");

                // Check if user exists
                $stmt = $pdo->prepare("SELECT id FROM admin_users WHERE username = ?");
                $stmt->execute([$username]);
                if ($stmt->fetch()) {
                    $error = 'Username already exists';
                } else {
                    // Create admin user
                    $hash = password_hash($password, PASSWORD_DEFAULT);
                    $stmt = $pdo->prepare("INSERT INTO admin_users (username, password_hash) VALUES (?, ?)");
                    $stmt->execute([$username, $hash]);
                    $message = "Admin user '$username' created successfully!";
                }
            } catch (PDOException $e) {
                $error = 'Database error: ' . $e->getMessage();
            }
        }
    }

    if ($action === 'run_migrations') {
        try {
            $pdo = db();

            // Add alias columns to pi_devices
            $pdo->exec("
                ALTER TABLE pi_devices
                ADD COLUMN alias VARCHAR(100) DEFAULT NULL,
                ADD COLUMN alias_updated_at TIMESTAMP NULL
            ");
            $message = 'Alias migration completed!';
        } catch (PDOException $e) {
            if (strpos($e->getMessage(), 'Duplicate column') !== false) {
                $message = 'Alias columns already exist - no changes needed.';
            } else {
                $error = 'Migration error: ' . $e->getMessage();
            }
        }
    }
}

// Check current state
$pdo = db();
$admin_exists = false;
$alias_exists = false;

try {
    $stmt = $pdo->query("SELECT COUNT(*) FROM admin_users");
    $admin_exists = $stmt->fetchColumn() > 0;
} catch (PDOException $e) {
    // Table doesn't exist
}

try {
    $stmt = $pdo->query("SHOW COLUMNS FROM pi_devices LIKE 'alias'");
    $alias_exists = $stmt->rowCount() > 0;
} catch (PDOException $e) {
    // Table doesn't exist or error
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Setup - PoolAIssistant Admin</title>
    <style>
        :root { --bg: #0f172a; --surface: #1e293b; --accent: #3b82f6; --text: #f1f5f9; --success: #22c55e; --danger: #ef4444; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 40px 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { margin-bottom: 30px; }
        h1 span { color: var(--accent); }
        .card { background: var(--surface); padding: 24px; border-radius: 12px; margin-bottom: 24px; }
        .card h2 { font-size: 1.125rem; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        .status { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .status.done { background: rgba(34,197,94,0.2); color: var(--success); }
        .status.pending { background: rgba(245,158,11,0.2); color: #f59e0b; }
        .form-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 6px; font-size: 0.875rem; color: #94a3b8; }
        input { width: 100%; padding: 10px 14px; border: 1px solid #475569; border-radius: 6px; background: var(--bg); color: var(--text); }
        input:focus { outline: none; border-color: var(--accent); }
        .btn { padding: 10px 20px; border: none; border-radius: 6px; background: var(--accent); color: white; cursor: pointer; font-weight: 600; }
        .btn:hover { background: #2563eb; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .message { padding: 12px; border-radius: 8px; margin-bottom: 20px; }
        .message.success { background: rgba(34,197,94,0.1); color: var(--success); }
        .message.error { background: rgba(239,68,68,0.1); color: var(--danger); }
        .warning { background: rgba(245,158,11,0.1); color: #f59e0b; padding: 16px; border-radius: 8px; margin-top: 24px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Pool<span>AI</span>ssistant Setup</h1>

        <?php if ($message): ?>
            <div class="message success"><?= htmlspecialchars($message) ?></div>
        <?php endif; ?>

        <?php if ($error): ?>
            <div class="message error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <div class="card">
            <h2>
                Database Migrations
                <span class="status <?= $alias_exists ? 'done' : 'pending' ?>"><?= $alias_exists ? 'Done' : 'Pending' ?></span>
            </h2>
            <p style="color: #94a3b8; margin-bottom: 16px;">Adds device alias columns for nickname support.</p>
            <form method="POST">
                <input type="hidden" name="action" value="run_migrations">
                <button type="submit" class="btn" <?= $alias_exists ? 'disabled' : '' ?>>
                    <?= $alias_exists ? 'Already Applied' : 'Run Migrations' ?>
                </button>
            </form>
        </div>

        <div class="card">
            <h2>
                Admin User
                <span class="status <?= $admin_exists ? 'done' : 'pending' ?>"><?= $admin_exists ? 'Exists' : 'Not Created' ?></span>
            </h2>
            <form method="POST">
                <input type="hidden" name="action" value="create_admin">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" name="username" required placeholder="admin">
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" name="password" required minlength="8">
                </div>
                <div class="form-group">
                    <label>Confirm Password</label>
                    <input type="password" name="confirm" required>
                </div>
                <button type="submit" class="btn">Create Admin User</button>
            </form>
        </div>

        <div class="warning">
            <strong>Security Notice:</strong> Delete this setup.php file after completing setup to prevent unauthorized access.
        </div>
    </div>
</body>
</html>
