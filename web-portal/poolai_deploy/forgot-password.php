<?php
/**
 * PoolAIssistant Portal - Forgot Password Page
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();
$auth->requireGuest();

$error = '';
$success = '';

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $email = $_POST['email'] ?? '';
    $csrf = $_POST['csrf_token'] ?? '';

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
    } else {
        $result = $auth->requestPasswordReset($email);
        // Always show success to prevent email enumeration
        $success = $result['message'];
    }
}

$csrfToken = $auth->generateCSRFToken();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forgot Password - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
</head>
<body class="auth-page">
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-logo">
                <h1>PoolAIssistant</h1>
                <p>Reset Your Password</p>
            </div>

            <?php if ($error): ?>
                <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>

            <?php if ($success): ?>
                <div class="alert alert-success"><?= htmlspecialchars($success) ?></div>
            <?php else: ?>
                <p class="auth-description">
                    Enter your email address and we'll send you a link to reset your password.
                </p>

                <form method="POST" class="auth-form">
                    <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">

                    <div class="form-group">
                        <label for="email">Email Address</label>
                        <input type="email" id="email" name="email" required autofocus>
                    </div>

                    <button type="submit" class="btn btn-primary btn-block">Send Reset Link</button>
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
