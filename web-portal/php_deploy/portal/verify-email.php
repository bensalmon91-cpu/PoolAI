<?php
/**
 * PoolAIssistant Portal - Email Verification Page
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();

$error = '';
$success = '';
$token = $_GET['token'] ?? '';

if (empty($token)) {
    $error = 'Invalid verification link.';
} else {
    $result = $auth->verifyEmail($token);

    if ($result['ok']) {
        header('Location: login.php?verified=1');
        exit;
    } else {
        $error = $result['error'];
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Email - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
</head>
<body class="auth-page">
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-logo">
                <h1>PoolAIssistant</h1>
                <p>Email Verification</p>
            </div>

            <?php if ($error): ?>
                <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
                <p class="auth-description">
                    The verification link may have expired or already been used.
                </p>
            <?php endif; ?>

            <div class="auth-links">
                <a href="login.php">Go to Login</a>
                <span class="divider">|</span>
                <a href="register.php">Create New Account</a>
            </div>
        </div>

        <div class="auth-footer">
            <p>&copy; <?= date('Y') ?> PoolAIssistant. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
