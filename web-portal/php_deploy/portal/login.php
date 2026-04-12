<?php
/**
 * PoolAIssistant Portal - Login Page
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();
$auth->requireGuest();

$error = '';
$success = '';

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $email = $_POST['email'] ?? '';
    $password = $_POST['password'] ?? '';
    $csrf = $_POST['csrf_token'] ?? '';

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
    } else {
        $result = $auth->login($email, $password);

        if ($result['ok']) {
            header('Location: dashboard.php');
            exit;
        } else {
            $error = $result['error'];
        }
    }
}

// Check for messages from other pages
if (isset($_GET['verified'])) {
    $success = 'Email verified successfully. You can now log in.';
}
if (isset($_GET['reset'])) {
    $success = 'Password reset successfully. You can now log in.';
}
if (isset($_GET['registered'])) {
    $success = 'Account created. Please check your email to verify your account.';
}

$csrfToken = $auth->generateCSRFToken();
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
</head>
<body class="auth-page">
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-logo">
                <h1>PoolAIssistant</h1>
                <p>Customer Portal</p>
            </div>

            <?php if ($error): ?>
                <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>

            <?php if ($success): ?>
                <div class="alert alert-success"><?= htmlspecialchars($success) ?></div>
            <?php endif; ?>

            <form method="POST" class="auth-form">
                <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required autofocus
                           value="<?= htmlspecialchars($_POST['email'] ?? '') ?>">
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>

                <button type="submit" class="btn btn-primary btn-block">Log In</button>
            </form>

            <div class="auth-links">
                <a href="forgot-password.php">Forgot your password?</a>
                <span class="divider">|</span>
                <a href="register.php">Create an account</a>
            </div>
        </div>

        <div class="auth-footer">
            <p>&copy; <?= date('Y') ?> PoolAIssistant. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
