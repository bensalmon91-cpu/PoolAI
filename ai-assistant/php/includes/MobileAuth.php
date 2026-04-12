<?php
/**
 * PoolAIssistant Mobile Authentication Class
 *
 * Handles JWT-based authentication for the mobile app.
 * Uses HMAC-SHA256 for token signing (no external dependencies).
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../config/config.php';

// Mobile-specific configuration
define('MOBILE_ACCESS_TOKEN_EXPIRY', 60 * 60);           // 1 hour
define('MOBILE_REFRESH_TOKEN_EXPIRY', 60 * 60 * 24 * 30); // 30 days
define('MOBILE_PASSWORD_MIN_LENGTH', 8);
define('MOBILE_BCRYPT_COST', 12);
define('MOBILE_MAX_LOGIN_ATTEMPTS', 5);
define('MOBILE_LOGIN_LOCKOUT_MINUTES', 15);

class MobileAuth {
    private $pdo;
    private $jwtSecret;

    public function __construct() {
        $this->pdo = db();
        $this->jwtSecret = env('JWT_SECRET', env('BOOTSTRAP_SECRET', 'fallback-secret-change-me'));
    }

    // =========================================================================
    // JWT Token Methods
    // =========================================================================

    /**
     * Generate a JWT access token
     */
    public function generateAccessToken(int $userId, string $email): string {
        $payload = [
            'sub' => $userId,
            'email' => $email,
            'type' => 'access',
            'iat' => time(),
            'exp' => time() + MOBILE_ACCESS_TOKEN_EXPIRY
        ];
        return $this->encodeJWT($payload);
    }

    /**
     * Generate a refresh token and store its hash
     */
    public function generateRefreshToken(int $userId, string $platform, string $deviceInfo = '', string $ip = ''): string {
        // Generate random refresh token
        $refreshToken = bin2hex(random_bytes(32));
        $tokenHash = hash('sha256', $refreshToken);

        $expiresAt = date('Y-m-d H:i:s', time() + MOBILE_REFRESH_TOKEN_EXPIRY);

        // Store in database
        $stmt = $this->pdo->prepare("
            INSERT INTO mobile_tokens (user_id, token_hash, platform, device_info, ip_address, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ");
        $stmt->execute([$userId, $tokenHash, $platform, $deviceInfo, $ip, $expiresAt]);

        return $refreshToken;
    }

    /**
     * Validate an access token and return the payload
     */
    public function validateAccessToken(string $token): ?array {
        $payload = $this->decodeJWT($token);

        if (!$payload) {
            return null;
        }

        // Check token type
        if (($payload['type'] ?? '') !== 'access') {
            return null;
        }

        // Check expiration
        if (($payload['exp'] ?? 0) < time()) {
            return null;
        }

        return $payload;
    }

    /**
     * Validate a refresh token and return user data
     */
    public function validateRefreshToken(string $refreshToken): ?array {
        $tokenHash = hash('sha256', $refreshToken);

        $stmt = $this->pdo->prepare("
            SELECT mt.id, mt.user_id, mt.expires_at, mt.revoked_at,
                   pu.email, pu.name, pu.status, pu.email_verified
            FROM mobile_tokens mt
            JOIN portal_users pu ON mt.user_id = pu.id
            WHERE mt.token_hash = ?
        ");
        $stmt->execute([$tokenHash]);
        $result = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$result) {
            return null;
        }

        // Check if revoked
        if ($result['revoked_at'] !== null) {
            return null;
        }

        // Check expiration
        if (strtotime($result['expires_at']) < time()) {
            return null;
        }

        // Check user status
        if ($result['status'] !== 'active' || !$result['email_verified']) {
            return null;
        }

        // Update last used
        $stmt = $this->pdo->prepare("UPDATE mobile_tokens SET last_used_at = NOW() WHERE id = ?");
        $stmt->execute([$result['id']]);

        return [
            'token_id' => $result['id'],
            'user_id' => $result['user_id'],
            'email' => $result['email'],
            'name' => $result['name']
        ];
    }

    /**
     * Revoke a refresh token
     */
    public function revokeRefreshToken(string $refreshToken): bool {
        $tokenHash = hash('sha256', $refreshToken);

        $stmt = $this->pdo->prepare("
            UPDATE mobile_tokens SET revoked_at = NOW() WHERE token_hash = ?
        ");
        return $stmt->execute([$tokenHash]) && $stmt->rowCount() > 0;
    }

    /**
     * Revoke all refresh tokens for a user
     */
    public function revokeAllUserTokens(int $userId): bool {
        $stmt = $this->pdo->prepare("
            UPDATE mobile_tokens SET revoked_at = NOW()
            WHERE user_id = ? AND revoked_at IS NULL
        ");
        return $stmt->execute([$userId]);
    }

    // =========================================================================
    // Authentication Methods
    // =========================================================================

    /**
     * Register a new user
     */
    public function register(string $email, string $password, string $name = '', string $company = ''): array {
        $email = strtolower(trim($email));

        // Validate email
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            return ['ok' => false, 'error' => 'Invalid email address'];
        }

        // Check password length
        if (strlen($password) < MOBILE_PASSWORD_MIN_LENGTH) {
            return ['ok' => false, 'error' => 'Password must be at least ' . MOBILE_PASSWORD_MIN_LENGTH . ' characters'];
        }

        // Check if email exists
        $stmt = $this->pdo->prepare("SELECT id FROM portal_users WHERE email = ?");
        $stmt->execute([$email]);
        if ($stmt->fetch()) {
            return ['ok' => false, 'error' => 'An account with this email already exists'];
        }

        // Generate verification token
        $verifyToken = bin2hex(random_bytes(32));
        $verifyExpires = date('Y-m-d H:i:s', strtotime('+24 hours'));

        // Hash password
        $passwordHash = password_hash($password, PASSWORD_BCRYPT, ['cost' => MOBILE_BCRYPT_COST]);

        try {
            $stmt = $this->pdo->prepare("
                INSERT INTO portal_users (email, password_hash, name, company, email_verify_token, email_verify_expires, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            ");
            $stmt->execute([$email, $passwordHash, $name, $company, $verifyToken, $verifyExpires]);
            $userId = $this->pdo->lastInsertId();

            // Create default notification preferences
            $stmt = $this->pdo->prepare("INSERT IGNORE INTO user_notification_prefs (user_id) VALUES (?)");
            $stmt->execute([$userId]);

            // Log the registration
            $this->auditLog($userId, 'mobile_register', ['email' => $email]);

            // Send verification email
            $this->sendVerificationEmail($email, $name, $verifyToken);

            return ['ok' => true, 'message' => 'Account created. Please check your email to verify your account.'];
        } catch (PDOException $e) {
            error_log("Mobile registration error: " . $e->getMessage());
            return ['ok' => false, 'error' => 'Registration failed. Please try again.'];
        }
    }

    /**
     * Login user and return tokens
     */
    public function login(string $email, string $password, string $platform, string $deviceInfo = ''): array {
        $email = strtolower(trim($email));
        $ip = $_SERVER['REMOTE_ADDR'] ?? '';

        // Check rate limiting
        if ($this->isRateLimited($email, $ip)) {
            return ['ok' => false, 'error' => 'Too many login attempts. Please try again later.'];
        }

        // Get user
        $stmt = $this->pdo->prepare("
            SELECT id, email, password_hash, name, company, status, email_verified
            FROM portal_users
            WHERE email = ?
        ");
        $stmt->execute([$email]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        // Record failed attempt (will be updated if successful)
        $this->recordLoginAttempt($email, $ip, false);

        if (!$user) {
            return ['ok' => false, 'error' => 'Invalid email or password'];
        }

        if (!password_verify($password, $user['password_hash'])) {
            return ['ok' => false, 'error' => 'Invalid email or password'];
        }

        if ($user['status'] === 'suspended') {
            return ['ok' => false, 'error' => 'Your account has been suspended. Please contact support.'];
        }

        if (!$user['email_verified']) {
            return ['ok' => false, 'error' => 'Please verify your email address before logging in.', 'unverified' => true];
        }

        // Update login attempt as successful
        $this->recordLoginAttempt($email, $ip, true);

        // Generate tokens
        $accessToken = $this->generateAccessToken($user['id'], $user['email']);
        $refreshToken = $this->generateRefreshToken($user['id'], $platform, $deviceInfo, $ip);

        // Update last login
        $stmt = $this->pdo->prepare("UPDATE portal_users SET last_login_at = NOW() WHERE id = ?");
        $stmt->execute([$user['id']]);

        $this->auditLog($user['id'], 'mobile_login', ['platform' => $platform, 'ip' => $ip]);

        return [
            'ok' => true,
            'access_token' => $accessToken,
            'refresh_token' => $refreshToken,
            'expires_in' => MOBILE_ACCESS_TOKEN_EXPIRY,
            'user' => [
                'id' => $user['id'],
                'email' => $user['email'],
                'name' => $user['name'],
                'company' => $user['company'] ?? ''
            ]
        ];
    }

    /**
     * Refresh access token using refresh token
     */
    public function refresh(string $refreshToken): array {
        $tokenData = $this->validateRefreshToken($refreshToken);

        if (!$tokenData) {
            return ['ok' => false, 'error' => 'Invalid or expired refresh token'];
        }

        $accessToken = $this->generateAccessToken($tokenData['user_id'], $tokenData['email']);

        return [
            'ok' => true,
            'access_token' => $accessToken,
            'expires_in' => MOBILE_ACCESS_TOKEN_EXPIRY
        ];
    }

    /**
     * Logout by revoking refresh token
     */
    public function logout(string $refreshToken, int $userId): array {
        $this->revokeRefreshToken($refreshToken);
        $this->auditLog($userId, 'mobile_logout', []);
        return ['ok' => true];
    }

    /**
     * Request password reset
     */
    public function requestPasswordReset(string $email): array {
        $email = strtolower(trim($email));

        $stmt = $this->pdo->prepare("SELECT id, name FROM portal_users WHERE email = ?");
        $stmt->execute([$email]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        // Always return success to prevent email enumeration
        if (!$user) {
            return ['ok' => true, 'message' => 'If an account exists with this email, you will receive a password reset link.'];
        }

        $resetToken = bin2hex(random_bytes(32));
        $resetExpires = date('Y-m-d H:i:s', strtotime('+1 hour'));

        $stmt = $this->pdo->prepare("
            UPDATE portal_users SET password_reset_token = ?, password_reset_expires = ? WHERE id = ?
        ");
        $stmt->execute([$resetToken, $resetExpires, $user['id']]);

        $this->sendPasswordResetEmail($email, $user['name'], $resetToken);
        $this->auditLog($user['id'], 'mobile_password_reset_requested', []);

        return ['ok' => true, 'message' => 'If an account exists with this email, you will receive a password reset link.'];
    }

    /**
     * Reset password with token
     */
    public function resetPassword(string $token, string $newPassword): array {
        if (strlen($newPassword) < MOBILE_PASSWORD_MIN_LENGTH) {
            return ['ok' => false, 'error' => 'Password must be at least ' . MOBILE_PASSWORD_MIN_LENGTH . ' characters'];
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

        $passwordHash = password_hash($newPassword, PASSWORD_BCRYPT, ['cost' => MOBILE_BCRYPT_COST]);

        $stmt = $this->pdo->prepare("
            UPDATE portal_users
            SET password_hash = ?, password_reset_token = NULL, password_reset_expires = NULL
            WHERE id = ?
        ");
        $stmt->execute([$passwordHash, $user['id']]);

        // Revoke all existing tokens for security
        $this->revokeAllUserTokens($user['id']);

        $this->auditLog($user['id'], 'mobile_password_reset', []);

        return ['ok' => true, 'message' => 'Password reset successfully. Please log in with your new password.'];
    }

    /**
     * Change password (authenticated user)
     */
    public function changePassword(int $userId, string $currentPassword, string $newPassword): array {
        if (strlen($newPassword) < MOBILE_PASSWORD_MIN_LENGTH) {
            return ['ok' => false, 'error' => 'Password must be at least ' . MOBILE_PASSWORD_MIN_LENGTH . ' characters'];
        }

        $stmt = $this->pdo->prepare("SELECT password_hash FROM portal_users WHERE id = ?");
        $stmt->execute([$userId]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$user || !password_verify($currentPassword, $user['password_hash'])) {
            return ['ok' => false, 'error' => 'Current password is incorrect'];
        }

        $passwordHash = password_hash($newPassword, PASSWORD_BCRYPT, ['cost' => MOBILE_BCRYPT_COST]);

        $stmt = $this->pdo->prepare("UPDATE portal_users SET password_hash = ? WHERE id = ?");
        $stmt->execute([$passwordHash, $userId]);

        $this->auditLog($userId, 'mobile_password_changed', []);

        return ['ok' => true, 'message' => 'Password changed successfully.'];
    }

    /**
     * Get user by ID
     */
    public function getUser(int $userId): ?array {
        $stmt = $this->pdo->prepare("
            SELECT id, email, name, company, phone, status, created_at, last_login_at
            FROM portal_users
            WHERE id = ? AND status = 'active'
        ");
        $stmt->execute([$userId]);
        return $stmt->fetch(PDO::FETCH_ASSOC) ?: null;
    }

    /**
     * Update user profile
     */
    public function updateProfile(int $userId, array $data): array {
        $allowedFields = ['name', 'company', 'phone'];
        $updates = [];
        $params = [];

        foreach ($allowedFields as $field) {
            if (isset($data[$field])) {
                $updates[] = "$field = ?";
                $params[] = trim($data[$field]);
            }
        }

        if (empty($updates)) {
            return ['ok' => false, 'error' => 'No valid fields to update'];
        }

        $params[] = $userId;

        $stmt = $this->pdo->prepare("UPDATE portal_users SET " . implode(', ', $updates) . " WHERE id = ?");
        $stmt->execute($params);

        $this->auditLog($userId, 'mobile_profile_updated', array_keys($data));

        return ['ok' => true, 'user' => $this->getUser($userId)];
    }

    // =========================================================================
    // Helper Methods
    // =========================================================================

    /**
     * Encode a JWT token
     */
    private function encodeJWT(array $payload): string {
        $header = ['typ' => 'JWT', 'alg' => 'HS256'];

        $headerEncoded = $this->base64UrlEncode(json_encode($header));
        $payloadEncoded = $this->base64UrlEncode(json_encode($payload));

        $signature = hash_hmac('sha256', "$headerEncoded.$payloadEncoded", $this->jwtSecret, true);
        $signatureEncoded = $this->base64UrlEncode($signature);

        return "$headerEncoded.$payloadEncoded.$signatureEncoded";
    }

    /**
     * Decode and validate a JWT token
     */
    private function decodeJWT(string $token): ?array {
        $parts = explode('.', $token);
        if (count($parts) !== 3) {
            return null;
        }

        list($headerEncoded, $payloadEncoded, $signatureEncoded) = $parts;

        // Verify signature
        $signature = $this->base64UrlDecode($signatureEncoded);
        $expectedSignature = hash_hmac('sha256', "$headerEncoded.$payloadEncoded", $this->jwtSecret, true);

        if (!hash_equals($expectedSignature, $signature)) {
            return null;
        }

        // Decode payload
        $payload = json_decode($this->base64UrlDecode($payloadEncoded), true);
        if (!$payload) {
            return null;
        }

        return $payload;
    }

    private function base64UrlEncode(string $data): string {
        return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
    }

    private function base64UrlDecode(string $data): string {
        return base64_decode(strtr($data, '-_', '+/'));
    }

    /**
     * Check rate limiting
     */
    private function isRateLimited(string $email, string $ip): bool {
        $since = date('Y-m-d H:i:s', strtotime('-' . MOBILE_LOGIN_LOCKOUT_MINUTES . ' minutes'));

        $stmt = $this->pdo->prepare("
            SELECT COUNT(*) as attempts FROM portal_login_attempts
            WHERE (email = ? OR ip_address = ?) AND attempted_at > ? AND success = 0
        ");
        $stmt->execute([$email, $ip, $since]);
        $result = $stmt->fetch(PDO::FETCH_ASSOC);

        return $result['attempts'] >= MOBILE_MAX_LOGIN_ATTEMPTS;
    }

    /**
     * Record login attempt
     */
    private function recordLoginAttempt(string $email, string $ip, bool $success): void {
        $stmt = $this->pdo->prepare("
            INSERT INTO portal_login_attempts (email, ip_address, success)
            VALUES (?, ?, ?)
        ");
        $stmt->execute([$email, $ip, $success ? 1 : 0]);
    }

    /**
     * Add audit log entry
     */
    private function auditLog(int $userId, string $action, $details): void {
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
    private function sendVerificationEmail(string $email, string $name, string $token): void {
        $verifyUrl = "https://poolai.modprojects.co.uk/verify-email.php?token=" . urlencode($token);
        $subject = "Verify your PoolAIssistant account";

        $body = "Hi " . ($name ?: 'there') . ",\n\n";
        $body .= "Welcome to PoolAIssistant! Please verify your email address by clicking the link below:\n\n";
        $body .= $verifyUrl . "\n\n";
        $body .= "This link will expire in 24 hours.\n\n";
        $body .= "If you didn't create an account, you can safely ignore this email.\n\n";
        $body .= "Best regards,\nThe PoolAIssistant Team";

        $this->sendEmail($email, $subject, $body);
    }

    /**
     * Send password reset email
     */
    private function sendPasswordResetEmail(string $email, string $name, string $token): void {
        $resetUrl = "https://poolai.modprojects.co.uk/reset-password.php?token=" . urlencode($token);
        $subject = "Reset your PoolAIssistant password";

        $body = "Hi " . ($name ?: 'there') . ",\n\n";
        $body .= "We received a request to reset your password. Click the link below to set a new password:\n\n";
        $body .= $resetUrl . "\n\n";
        $body .= "This link will expire in 1 hour.\n\n";
        $body .= "If you didn't request this, you can safely ignore this email.\n\n";
        $body .= "Best regards,\nThe PoolAIssistant Team";

        $this->sendEmail($email, $subject, $body);
    }

    /**
     * Send email
     */
    private function sendEmail(string $to, string $subject, string $body): bool {
        $headers = [
            'From' => 'PoolAIssistant <noreply@poolaissistant.modprojects.co.uk>',
            'Reply-To' => 'noreply@poolaissistant.modprojects.co.uk',
            'X-Mailer' => 'PHP/' . phpversion(),
            'Content-Type' => 'text/plain; charset=UTF-8'
        ];

        $headerStr = '';
        foreach ($headers as $key => $value) {
            $headerStr .= "$key: $value\r\n";
        }

        $result = mail($to, $subject, $body, $headerStr);

        if (!$result) {
            error_log("Failed to send email to: $to");
        }

        return $result;
    }

    // =========================================================================
    // Middleware Helper
    // =========================================================================

    /**
     * Authenticate request from Authorization header
     * Returns user data if valid, sends error response and exits if not
     */
    public function requireAuth(): array {
        $authHeader = $_SERVER['HTTP_AUTHORIZATION'] ?? '';

        if (stripos($authHeader, 'Bearer ') !== 0) {
            http_response_code(401);
            header('Content-Type: application/json');
            echo json_encode(['ok' => false, 'error' => 'Authorization header required']);
            exit;
        }

        $token = substr($authHeader, 7);
        $payload = $this->validateAccessToken($token);

        if (!$payload) {
            http_response_code(401);
            header('Content-Type: application/json');
            echo json_encode(['ok' => false, 'error' => 'Invalid or expired token']);
            exit;
        }

        // Get fresh user data
        $user = $this->getUser($payload['sub']);
        if (!$user) {
            http_response_code(401);
            header('Content-Type: application/json');
            echo json_encode(['ok' => false, 'error' => 'User not found or inactive']);
            exit;
        }

        return $user;
    }
}
