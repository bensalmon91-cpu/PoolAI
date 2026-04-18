<?php
/**
 * Staff PWA Login
 *
 * Verifies credentials against admin_users directly so this page does not
 * depend on a loginAdmin() helper (the production auth.php predates it).
 */

ini_set('display_errors', 1);
error_reporting(E_ALL);

require_once __DIR__ . '/../includes/auth.php';

$error = '';

if (isAdmin()) {
    header('Location: /staff/');
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
                header('Location: /staff/');
                exit;
            }
            $error = 'Invalid username or password';
        } catch (Throwable $e) {
            error_log('staff/login.php: ' . $e->getMessage());
            $error = 'Login error. Please try again.';
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#0f172a">
    <title>Staff Sign In - PoolAIssistant</title>
    <link rel="manifest" href="/staff/manifest.json">
    <link rel="icon" href="/staff/icon.php?size=192" type="image/png">
    <link rel="apple-touch-icon" href="/staff/icon.php?size=192">
    <link rel="stylesheet" href="/staff/assets/styles.css">
</head>
<body class="auth-body">
    <main class="auth-card">
        <div class="auth-brand">
            <div class="auth-logo"><span>P</span></div>
            <h1>Pool<span class="accent">AI</span> Staff</h1>
            <p class="muted">Operations &amp; AI governance</p>
        </div>

        <?php if ($error): ?>
            <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <form method="POST" class="form">
            <label class="field">
                <span>Username</span>
                <input type="text" name="username" autocomplete="username" required autofocus>
            </label>
            <label class="field">
                <span>Password</span>
                <input type="password" name="password" autocomplete="current-password" required>
            </label>
            <button type="submit" class="btn btn-primary btn-block">Sign in</button>
        </form>

        <p class="auth-foot muted">
            Staff accounts share the admin login.
            <a href="/admin/">Full admin panel</a>
        </p>
    </main>
</body>
</html>
