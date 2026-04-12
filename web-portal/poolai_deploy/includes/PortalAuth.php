<?php
/**
 * PoolAIssistant Portal Authentication Class
 */

require_once __DIR__ . '/../config/portal.php';
require_once __DIR__ . '/../config/database.php';

class PortalAuth {
    private $pdo;
    private $user = null;

    public function __construct() {
        $this->pdo = db();
        $this->initSession();
    }

    /**
     * Initialize session with secure settings
     */
    private function initSession() {
        if (session_status() === PHP_SESSION_NONE) {
            session_name(PORTAL_SESSION_NAME);
            session_set_cookie_params([
                'lifetime' => PORTAL_SESSION_LIFETIME,
                'path' => '/',
                'domain' => '',
                'secure' => PORTAL_SESSION_SECURE,
                'httponly' => true,
                'samesite' => 'Lax'
            ]);
            session_start();
        }

        // Check if user is logged in
        if (isset($_SESSION['portal_user_id'])) {
            $this->loadUser($_SESSION['portal_user_id']);
        }
    }

    /**
     * Load user data from database
     */
    private function loadUser($userId) {
        $stmt = $this->pdo->prepare("
            SELECT id, email, name, company, status, email_verified, created_at, last_login_at
            FROM portal_users
            WHERE id = ? AND status = 'active'
        ");
        $stmt->execute([$userId]);
        $this->user = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$this->user) {
            $this->logout();
        }
    }

    /**
     * Register a new user
     */
    public function register($email, $password, $name = '', $company = '') {
        $email = strtolower(trim($email));

        // Validate email
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return ['ok' => false, 'error' => 'Invalid email address'];
        }

        // Check password length
        if (strlen($password) < PORTAL_PASSWORD_MIN_LENGTH) {
            return ['ok' => false, 'error' => 'Password must be at least ' . PORTAL_PASSWORD_MIN_LENGTH . ' characters'];
        }

        // Check if email exists
        $stmt = $this->pdo->prepare("SELECT id FROM portal_users WHERE email = ?");
        $stmt->execute([$email]);
        if ($stmt->fetch()) {
            return ['ok' => false, 'error' => 'An account with this email already exists'];
        }

        // Generate verification token
        $verifyToken = bin2hex(random_bytes(32));
        $verifyExpires = date('Y-m-d H:i:s', strtotime('+' . PORTAL_EMAIL_VERIFY_HOURS . ' hours'));

        // Hash password
        $passwordHash = password_hash($password, PASSWORD_BCRYPT, ['cost' => PORTAL_PASSWORD_BCRYPT_COST]);

        // Insert user
        $stmt = $this->pdo->prepare("
            INSERT INTO portal_users (email, password_hash, name, company, email_verify_token, email_verify_expires, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ");

        try {
            $stmt->execute([$email, $passwordHash, $name, $company, $verifyToken, $verifyExpires]);
            $userId = $this->pdo->lastInsertId();

            // Log the registration
            $this->auditLog($userId, 'register', ['email' => $email]);

            // Send verification email
            $this->sendVerificationEmail($email, $name, $verifyToken);

            return ['ok' => true, 'message' => 'Account created. Please check your email to verify your account.'];
        } catch (PDOException $e) {
            error_log("Portal registration error: " . $e->getMessage());
            return ['ok' => false, 'error' => 'Registration failed. Please try again.'];
        }
    }

    /**
     * Login user
     */
    public function login($email, $password, $rememberMe = false) {
        $email = strtolower(trim($email));
        $ip = $_SERVER['REMOTE_ADDR'] ?? '';

        // Check rate limiting
        if ($this->isRateLimited($email, $ip)) {
            return ['ok' => false, 'error' => 'Too many login attempts. Please try again in ' . PORTAL_LOGIN_LOCKOUT_MINUTES . ' minutes.'];
        }

        // Get user
        $stmt = $this->pdo->prepare("
            SELECT id, email, password_hash, name, status, email_verified
            FROM portal_users
            WHERE email = ?
        ");
        $stmt->execute([$email]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        // Record attempt
        $this->recordLoginAttempt($email, $ip, false);

        if (!$user) {
            return ['ok' => false, 'error' => 'Invalid email or password'];
        }

        // Check password
        if (!password_verify($password, $user['password_hash'])) {
            return ['ok' => false, 'error' => 'Invalid email or password'];
        }

        // Check status
        if ($user['status'] === 'suspended') {
            return ['ok' => false, 'error' => 'Your account has been suspended. Please contact support.'];
        }

        // Check email verification
        if (!$user['email_verified']) {
            return ['ok' => false, 'error' => 'Please verify your email address before logging in.', 'unverified' => true];
        }

        // Update login attempt as successful
        $this->recordLoginAttempt($email, $ip, true);

        // Create session
        $_SESSION['portal_user_id'] = $user['id'];
        $_SESSION['portal_user_email'] = $user['email'];
        $_SESSION['portal_user_name'] = $user['name'];

        // Update last login
        $stmt = $this->pdo->prepare("UPDATE portal_users SET last_login_at = NOW() WHERE id = ?");
        $stmt->execute([$user['id']]);

        // Regenerate session ID for security
        session_regenerate_id(true);

        // Log the login
        $this->auditLog($user['id'], 'login', ['ip' => $ip]);

        $this->loadUser($user['id']);

        return ['ok' => true, 'user' => $this->getPublicUserData()];
    }

    /**
     * Logout user
     */
    public function logout() {
        if ($this->user) {
            $this->auditLog($this->user['id'], 'logout', []);
        }

        $_SESSION = [];

        if (ini_get("session.use_cookies")) {
            $params = session_get_cookie_params();
            setcookie(session_name(), '', time() - 42000,
                $params["path"], $params["domain"],
                $params["secure"], $params["httponly"]
            );
        }

        session_destroy();
        $this->user = null;

        return ['ok' => true];
    }

    /**
     * Check if user is logged in
     */
    public function isLoggedIn() {
        return $this->user !== null;
    }

    /**
     * Get current user
     */
    public function getUser() {
        return $this->user;
    }

    /**
     * Get public user data (safe to send to frontend)
     */
    public function getPublicUserData() {
        if (!$this->user) return null;
        return [
            'id' => $this->user['id'],
            'email' => $this->user['email'],
            'name' => $this->user['name'],
            'company' => $this->user['company'] ?? ''
        ];
    }

    /**
     * Verify email with token
     */
    public function verifyEmail($token) {
        $stmt = $this->pdo->prepare("
            SELECT id, email FROM portal_users
            WHERE email_verify_token = ? AND email_verify_expires > NOW() AND email_verified = 0
        ");
        $stmt->execute([$token]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$user) {
            return ['ok' => false, 'error' => 'Invalid or expired verification link'];
        }

        // Mark as verified
        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET email_verified = 1, email_verify_token = NULL, status = 'active'
            WHERE id = ?
        ");
        $stmt->execute([$user['id']]);

        $this->auditLog($user['id'], 'email_verified', []);

        return ['ok' => true, 'message' => 'Email verified successfully. You can now log in.'];
    }

    /**
     * Request password reset
     */
    public function requestPasswordReset($email) {
        $email = strtolower(trim($email));

        $stmt = $this->pdo->prepare("SELECT id, name FROM portal_users WHERE email = ?");
        $stmt->execute([$email]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        // Always return success to prevent email enumeration
        if (!$user) {
            return ['ok' => true, 'message' => 'If an account exists with this email, you will receive a password reset link.'];
        }

        // Generate reset token
        $resetToken = bin2hex(random_bytes(32));
        $resetExpires = date('Y-m-d H:i:s', strtotime('+' . PORTAL_PASSWORD_RESET_HOURS . ' hours'));

        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET password_reset_token = ?, password_reset_expires = ?
            WHERE id = ?
        ");
        $stmt->execute([$resetToken, $resetExpires, $user['id']]);

        // Send email
        $this->sendPasswordResetEmail($email, $user['name'], $resetToken);

        $this->auditLog($user['id'], 'password_reset_requested', []);

        return ['ok' => true, 'message' => 'If an account exists with this email, you will receive a password reset link.'];
    }

    /**
     * Reset password with token
     */
    public function resetPassword($token, $newPassword) {
        if (strlen($newPassword) < PORTAL_PASSWORD_MIN_LENGTH) {
            return ['ok' => false, 'error' => 'Password must be at least ' . PORTAL_PASSWORD_MIN_LENGTH . ' characters'];
        }

        $stmt = $this->pdo->prepare("
            SELECT id FROM portal_users
            WHERE password_reset_token = ? AND password_reset_expires > NOW()
        ");
        $stmt->execute([$token]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$user) {
            return ['ok' => false, 'error' => 'Invalid or expired reset link'];
        }

        // Update password
        $passwordHash = password_hash($newPassword, PASSWORD_BCRYPT, ['cost' => PORTAL_PASSWORD_BCRYPT_COST]);

        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET password_hash = ?, password_reset_token = NULL, password_reset_expires = NULL
            WHERE id = ?
        ");
        $stmt->execute([$passwordHash, $user['id']]);

        $this->auditLog($user['id'], 'password_reset', []);

        return ['ok' => true, 'message' => 'Password reset successfully. You can now log in.'];
    }

    /**
     * Check rate limiting for login attempts
     */
    private function isRateLimited($email, $ip) {
        $since = date('Y-m-d H:i:s', strtotime('-' . PORTAL_LOGIN_LOCKOUT_MINUTES . ' minutes'));

        $stmt = $this->pdo->prepare("
            SELECT COUNT(*) as attempts FROM portal_login_attempts
            WHERE (email = ? OR ip_address = ?) AND attempted_at > ? AND success = 0
        ");
        $stmt->execute([$email, $ip, $since]);
        $result = $stmt->fetch(PDO::FETCH_ASSOC);

        return $result['attempts'] >= PORTAL_MAX_LOGIN_ATTEMPTS;
    }

    /**
     * Record login attempt
     */
    private function recordLoginAttempt($email, $ip, $success) {
        $stmt = $this->pdo->prepare("
            INSERT INTO portal_login_attempts (email, ip_address, success)
            VALUES (?, ?, ?)
        ");
        $stmt->execute([$email, $ip, $success ? 1 : 0]);
    }

    /**
     * Add entry to audit log
     */
    private function auditLog($userId, $action, $details) {
        $stmt = $this->pdo->prepare("
            INSERT INTO portal_audit_log (user_id, action, details_json, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?)
        ");
        $stmt->execute([
            $userId,
            $action,
            json_encode($details),
            $_SERVER['REMOTE_ADDR'] ?? '',
            substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 500)
        ]);
    }

    /**
     * Send verification email
     */
    private function sendVerificationEmail($email, $name, $token) {
        $verifyUrl = PORTAL_BASE_URL . "/verify-email.php?token=" . urlencode($token);
        $subject = "Verify your PoolAIssistant account";

        $body = "Hi " . ($name ?: 'there') . ",\n\n";
        $body .= "Welcome to PoolAIssistant! Please verify your email address by clicking the link below:\n\n";
        $body .= $verifyUrl . "\n\n";
        $body .= "This link will expire in " . PORTAL_EMAIL_VERIFY_HOURS . " hours.\n\n";
        $body .= "If you didn't create an account, you can safely ignore this email.\n\n";
        $body .= "Best regards,\nThe PoolAIssistant Team";

        $this->sendEmail($email, $subject, $body);
    }

    /**
     * Send password reset email
     */
    private function sendPasswordResetEmail($email, $name, $token) {
        $resetUrl = PORTAL_BASE_URL . "/reset-password.php?token=" . urlencode($token);
        $subject = "Reset your PoolAIssistant password";

        $body = "Hi " . ($name ?: 'there') . ",\n\n";
        $body .= "We received a request to reset your password. Click the link below to set a new password:\n\n";
        $body .= $resetUrl . "\n\n";
        $body .= "This link will expire in " . PORTAL_PASSWORD_RESET_HOURS . " hour(s).\n\n";
        $body .= "If you didn't request this, you can safely ignore this email.\n\n";
        $body .= "Best regards,\nThe PoolAIssistant Team";

        $this->sendEmail($email, $subject, $body);
    }

    /**
     * Send email (basic implementation - enhance for production)
     */
    private function sendEmail($to, $subject, $body) {
        $headers = [
            'From' => PORTAL_EMAIL_FROM_NAME . ' <' . PORTAL_EMAIL_FROM . '>',
            'Reply-To' => PORTAL_EMAIL_FROM,
            'X-Mailer' => 'PHP/' . phpversion(),
            'Content-Type' => 'text/plain; charset=UTF-8'
        ];

        $headerStr = '';
        foreach ($headers as $key => $value) {
            $headerStr .= "$key: $value\r\n";
        }

        // Use mail() for simplicity - consider PHPMailer for production
        $result = mail($to, $subject, $body, $headerStr);

        if (!$result) {
            error_log("Failed to send email to: $to");
        }

        return $result;
    }

    /**
     * Generate CSRF token
     */
    public function generateCSRFToken() {
        if (!isset($_SESSION[PORTAL_CSRF_TOKEN_NAME])) {
            $_SESSION[PORTAL_CSRF_TOKEN_NAME] = bin2hex(random_bytes(32));
        }
        return $_SESSION[PORTAL_CSRF_TOKEN_NAME];
    }

    /**
     * Validate CSRF token
     */
    public function validateCSRFToken($token) {
        return isset($_SESSION[PORTAL_CSRF_TOKEN_NAME]) &&
               hash_equals($_SESSION[PORTAL_CSRF_TOKEN_NAME], $token);
    }

    /**
     * Require authentication - redirect to login if not logged in
     */
    public function requireAuth() {
        if (!$this->isLoggedIn()) {
            header('Location: ' . PORTAL_BASE_URL . '/login.php');
            exit;
        }
    }

    /**
     * Require guest - redirect to dashboard if logged in
     */
    public function requireGuest() {
        if ($this->isLoggedIn()) {
            header('Location: ' . PORTAL_BASE_URL . '/dashboard.php');
            exit;
        }
    }
}
