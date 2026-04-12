<?php
/**
 * Authentication helpers
 */

require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../config/database.php';

/**
 * Start session with secure settings
 */
function startSecureSession(): void {
    if (session_status() === PHP_SESSION_NONE) {
        session_name(SESSION_NAME);
        session_set_cookie_params([
            'lifetime' => SESSION_LIFETIME,
            'path' => '/',
            'secure' => isset($_SERVER['HTTPS']),
            'httponly' => true,
            'samesite' => 'Lax'
        ]);
        session_start();
    }
}

/**
 * Check if user is admin
 */
function isAdmin(): bool {
    startSecureSession();
    return !empty($_SESSION['admin_id']);
}

/**
 * Require admin authentication
 */
function requireAdmin(): void {
    startSecureSession();
    if (!isAdmin()) {
        if (strpos($_SERVER['HTTP_ACCEPT'] ?? '', 'application/json') !== false) {
            http_response_code(401);
            header('Content-Type: application/json');
            echo json_encode(['error' => 'Admin authentication required']);
            exit;
        }
        header('Location: /admin/login.php');
        exit;
    }
}

/**
 * Login admin user
 */
function loginAdmin(string $username, string $password): array {
    try {
        $pdo = db();

        // Check admin_users table
        $stmt = $pdo->prepare("SELECT id, username, password_hash FROM admin_users WHERE username = ?");
        $stmt->execute([$username]);
        $user = $stmt->fetch();

        if (!$user) {
            return ['success' => false, 'error' => 'Invalid username or password'];
        }

        if (!password_verify($password, $user['password_hash'])) {
            return ['success' => false, 'error' => 'Invalid username or password'];
        }

        // Start session and set admin
        startSecureSession();
        $_SESSION['admin_id'] = $user['id'];
        $_SESSION['admin_username'] = $user['username'];

        return ['success' => true];

    } catch (PDOException $e) {
        return ['success' => false, 'error' => 'Database error'];
    }
}

/**
 * Logout admin user
 */
function logoutAdmin(): void {
    startSecureSession();
    $_SESSION = [];
    session_destroy();
}

/**
 * Authenticate a Pi device by API key
 * Returns device array if valid, null otherwise
 */
function authenticateDevice(): ?array {
    // Get API key from header (support both X-API-Key and Authorization: Bearer)
    $api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
    if (empty($api_key)) {
        $auth_header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
        if (stripos($auth_header, 'Bearer ') === 0) {
            $api_key = substr($auth_header, 7);
        }
    }

    if (empty($api_key)) {
        return null;
    }

    try {
        $pdo = db();
        // Columns: id, device_uuid, name, api_key, is_active, last_seen
        $stmt = $pdo->prepare("SELECT id, device_uuid, name, api_key FROM pi_devices WHERE api_key = ? AND is_active = 1");
        $stmt->execute([$api_key]);
        $device = $stmt->fetch(PDO::FETCH_ASSOC);

        return $device ?: null;
    } catch (PDOException $e) {
        error_log("Device auth error: " . $e->getMessage());
        return null;
    }
}
