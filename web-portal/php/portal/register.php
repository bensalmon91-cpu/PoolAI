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

    if (!$auth->validateCSRFToken($csrf)) {
        $error = 'Invalid request. Please try again.';
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
