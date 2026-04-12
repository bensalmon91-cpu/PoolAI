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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Login - PoolAIssistant</title>

    <!-- PWA Meta Tags -->
    <meta name="theme-color" content="#0066cc">
    <meta name="description" content="Log in to PoolAIssistant - Monitor and control your pool">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="PoolAI">

    <!-- PWA Manifest -->
    <link rel="manifest" href="/manifest.json">

    <!-- Favicon & Icons -->
    <link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">

    <!-- Stylesheets -->
    <link rel="stylesheet" href="assets/css/portal.css">

    <!-- PWA Script -->
    <script src="/assets/js/pwa.js" defer></script>
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
                           placeholder="you@example.com"
                           value="<?= htmlspecialchars($_POST['email'] ?? '') ?>">
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required
                           placeholder="Enter your password">
                </div>

                <button type="submit" class="btn btn-primary btn-block">Log In</button>
            </form>

            <div class="auth-links">
                <a href="forgot-password.php">Forgot password?</a>
                <span class="divider">|</span>
                <a href="register.php">Create account</a>
            </div>

            <!-- Install App Prompt for Mobile -->
            <div id="installHint" style="display: none; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color); text-align: center;">
                <p style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 0.75rem;">For the best experience:</p>
                <a href="/install.php" class="btn btn-outline btn-block" style="font-size: 0.875rem;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 0.5rem;">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Install App
                </a>
            </div>
        </div>

        <div class="auth-footer">
            <p>&copy; <?= date('Y') ?> PoolAIssistant. All rights reserved.</p>
        </div>
    </div>

    <script>
        // Show install hint on mobile devices that aren't in standalone mode
        (function() {
            const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
            const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;

            if (isMobile && !isStandalone) {
                document.getElementById('installHint').style.display = 'block';
            }
        })();
    </script>
</body>
</html>
