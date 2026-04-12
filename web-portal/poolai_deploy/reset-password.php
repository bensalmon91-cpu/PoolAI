<?php
/**
 * PoolAIssistant Portal - Reset Password Page
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();
$auth->requireGuest();

$error = '';
$success = '';
$token = $_GET['token'] ?? '';
$validToken = false;

// Validate token exists
if (empty($token)) {
    $error = 'Invalid password reset link.';
} else {
    $validToken = true;
}

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $validToken) {
    $password = $_POST['password'] ?? '';
    $confirmPassword = $_POST['confirm_password'] ?? '';
    $csrf = $_POST['csrf_token'] ?? '';
    $token = $_POST['token'] ?? '';

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
    } elseif ($password !== $confirmPassword) {
        $error = 'Passwords do not match.';
    } else {
        $result = $auth->resetPassword($token, $password);

        if ($result['ok']) {
            header('Location: login.php?reset=1');
            exit;
        } else {
            $error = $result['error'];
        }
    }
}

$csrfToken = $auth->generateCSRFToken();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Password - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
</head>
<body class="auth-page">
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-logo">
                <h1>PoolAIssistant</h1>
                <p>Set New Password</p>
            </div>

            <?php if ($error): ?>
                <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>

            <?php if ($validToken && !$success): ?>
                <form method="POST" class="auth-form">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">
                    <input type="hidden" name="token" value="<?= htmlspecialchars($token) ?>">

                    <div class="form-group">
                        <label for="password">New Password</label>
                        <input type="password" id="password" name="password" required
                               minlength="<?= PORTAL_PASSWORD_MIN_LENGTH ?>">
                        <small>Minimum <?= PORTAL_PASSWORD_MIN_LENGTH ?> characters</small>
                    </div>

                    <div class="form-group">
                        <label for="confirm_password">Confirm New Password</label>
                        <input type="password" id="confirm_password" name="confirm_password" required>
                    </div>

                    <button type="submit" class="btn btn-primary btn-block">Reset Password</button>
                </form>
            <?php endif; ?>

            <div class="auth-links">
                <a href="login.php">Back to Login</a>
            </div>
        </div>

        <div class="auth-footer">
            <p>&copy; <?= date('Y') ?> PoolAIssistant. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
