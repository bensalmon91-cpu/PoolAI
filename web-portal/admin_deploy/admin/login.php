<?php
/**
 * Admin Login Page
 *
 * Verifies credentials against admin_users directly so this page does not
 * depend on a loginAdmin() helper (the production auth.php predates it).
 */

ini_set('display_errors', 1);
error_reporting(E_ALL);

require_once __DIR__ . '/../includes/auth.php';

$error = '';

if (isAdmin()) {
    header('Location: /admin/');
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';

    if ($username === '' || $password === '') {
        $error = 'Please enter username and password';
    } else {
        try {
            $pdo = db();
            $stmt = $pdo->prepare("SELECT id, username, password_hash FROM admin_users WHERE username = ?");
            $stmt->execute([$username]);
            $user = $stmt->fetch(PDO::FETCH_ASSOC);

            if ($user && password_verify($password, $user['password_hash'])) {
                startSecureSession();
                session_regenerate_id(true);
                $_SESSION['admin_id'] = (int)$user['id'];
                $_SESSION['admin_username'] = $user['username'];
                header('Location: /admin/');
                exit;
            }
            $error = 'Invalid username or password';
        } catch (Throwable $e) {
            error_log('admin/login.php: ' . $e->getMessage());
            $error = 'Login error. Please try again.';
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - PoolAIssistant</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --danger: #ef4444;
            --border: #475569;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-card {
            background: var(--surface);
            padding: 40px;
            border-radius: 16px;
            width: 100%;
            max-width: 400px;
        }
        h1 {
            text-align: center;
            margin-bottom: 8px;
            font-size: 1.5rem;
        }
        h1 span { color: var(--accent); }
        .subtitle {
            text-align: center;
            color: var(--text-muted);
            margin-bottom: 30px;
            font-size: 0.875rem;
        }
        .form-group { margin-bottom: 20px; }
        label {
            display: block;
            margin-bottom: 6px;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg);
            color: var(--text);
            font-size: 1rem;
        }
        input:focus {
            outline: none;
            border-color: var(--accent);
        }
        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: var(--accent);
            color: white;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s;
        }
        .btn:hover { background: var(--accent-hover); }
        .error {
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger);
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
            font-size: 0.875rem;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <h1>Pool<span>AI</span>ssistant</h1>
        <p class="subtitle">Admin Panel</p>

        <?php if ($error): ?>
            <div class="error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">Login</button>
        </form>
    </div>
</body>
</html>
