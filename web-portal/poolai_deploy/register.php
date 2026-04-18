<?php
/**
 * PoolAIssistant Portal - Registration Page
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();
$auth->requireGuest();

$error = '';
$formData = [
    'email' => '',
    'name' => '',
    'company' => ''
];

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $formData['email'] = $_POST['email'] ?? '';
    $formData['name'] = $_POST['name'] ?? '';
    $formData['company'] = $_POST['company'] ?? '';
    $password = $_POST['password'] ?? '';
    $confirmPassword = $_POST['confirm_password'] ?? '';
    $csrf = $_POST['csrf_token'] ?? '';

    $acceptedTos = !empty($_POST['accept_tos']);

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
    } elseif (!$acceptedTos) {
        $error = 'You must accept the Terms and Privacy Policy to create an account.';
    } elseif ($password !== $confirmPassword) {
        $error = 'Passwords do not match.';
    } else {
        $result = $auth->register(
            $formData['email'],
            $password,
            $formData['name'],
            $formData['company']
        );

        if ($result['ok']) {
            // Record the ToS acceptance. Looked up by email so we don't
            // have to extend PortalAuth::register(). Failure to record is
            // non-fatal but logged.
            try {
                $pdo = db();
                $pdo->exec("ALTER TABLE portal_users
                    ADD COLUMN IF NOT EXISTS tos_accepted_at TIMESTAMP NULL,
                    ADD COLUMN IF NOT EXISTS tos_accepted_version VARCHAR(32) NULL");
                $stmt = $pdo->prepare("UPDATE portal_users
                    SET tos_accepted_at = NOW(), tos_accepted_version = ?
                    WHERE email = ? AND tos_accepted_at IS NULL");
                $stmt->execute(['v1-' . date('Y-m-d'), strtolower(trim($formData['email']))]);
            } catch (Throwable $e) {
                error_log('register.php tos_accepted_at update failed: ' . $e->getMessage());
            }
            header('Location: login.php?registered=1');
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
    <title>Register - PoolAIssistant</title>
    <link rel="stylesheet" href="assets/css/portal.css">
</head>
<body class="auth-page">
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-logo">
                <h1>PoolAIssistant</h1>
                <p>Create Your Account</p>
            </div>

            <?php if ($error): ?>
                <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>

            <form method="POST" class="auth-form">
                <input type="hidden" name="csrf_token" value="<?= htmlspecialchars($csrfToken) ?>">

                <div class="form-group">
                    <label for="email">Email Address *</label>
                    <input type="email" id="email" name="email" required autofocus
                           value="<?= htmlspecialchars($formData['email']) ?>">
                </div>

                <div class="form-group">
                    <label for="name">Full Name</label>
                    <input type="text" id="name" name="name"
                           value="<?= htmlspecialchars($formData['name']) ?>">
                </div>

                <div class="form-group">
                    <label for="company">Company / Organisation</label>
                    <input type="text" id="company" name="company"
                           value="<?= htmlspecialchars($formData['company']) ?>">
                </div>

                <div class="form-group">
                    <label for="password">Password *</label>
                    <input type="password" id="password" name="password" required
                           minlength="<?= PORTAL_PASSWORD_MIN_LENGTH ?>">
                    <small>Minimum <?= PORTAL_PASSWORD_MIN_LENGTH ?> characters</small>
                </div>

                <div class="form-group">
                    <label for="confirm_password">Confirm Password *</label>
                    <input type="password" id="confirm_password" name="confirm_password" required>
                </div>

                <div class="form-group form-check" style="display:flex; gap:0.6rem; align-items:flex-start; margin: 1rem 0;">
                    <input type="checkbox" id="accept_tos" name="accept_tos" value="1" required
                           style="margin-top:0.25rem; flex-shrink:0;">
                    <label for="accept_tos" style="font-size:0.85rem; line-height:1.4;">
                        I have read and accept the
                        <a href="/terms.php" target="_blank" rel="noopener">Terms of Service</a>
                        and
                        <a href="/privacy.php" target="_blank" rel="noopener">Privacy Policy</a>,
                        and I understand that AI suggestions are advisory only.
                    </label>
                </div>

                <button type="submit" class="btn btn-primary btn-block">Create Account</button>
            </form>

            <div class="auth-links">
                <span>Already have an account?</span>
                <a href="login.php">Log in</a>
            </div>
        </div>

        <div class="auth-footer">
            <p>&copy; <?= date('Y') ?> PoolAIssistant. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
