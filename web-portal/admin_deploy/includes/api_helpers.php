<?php
/**
 * API Helper Functions
 */

/**
 * Set CORS headers for API responses
 */
function setCorsHeaders(): void {
    header('Access-Control-Allow-Origin: *');
    header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization, X-API-Key');

    if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
        http_response_code(204);
        exit;
    }
}

/**
 * Require specific HTTP method
 */
function requireMethod(string $method): void {
    if ($_SERVER['REQUEST_METHOD'] !== strtoupper($method)) {
        errorResponse('Method not allowed', 405);
    }
}

/**
 * Validate required fields exist in data
 */
function validateRequired(array $fields, array $data): ?string {
    foreach ($fields as $field) {
        if (empty($data[$field])) {
            return "Missing required field: $field";
        }
    }
    return null;
}

/**
 * Send JSON response and exit
 */
function jsonResponse($data, int $statusCode = 200): void {
    http_response_code($statusCode);
    header('Content-Type: application/json');
    echo json_encode($data);
    exit;
}

/**
 * Send success response and exit
 */
function successResponse(array $data = [], string $message = 'Success'): void {
    jsonResponse(array_merge(['ok' => true, 'message' => $message], $data));
}

/**
 * Send error response and exit
 */
function errorResponse(string $message, int $statusCode = 400): void {
    jsonResponse(['ok' => false, 'error' => $message], $statusCode);
}

/**
 * Get JSON input from request body
 */
function getJsonInput(): array {
    $input = file_get_contents('php://input');
    if (empty($input)) {
        return [];
    }

    $data = json_decode($input, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        errorResponse('Invalid JSON input');
    }

    return $data ?? [];
}

/**
 * Read an X-API-Key (or Authorization: Bearer ...) header from the request.
 *
 * Returns the token string, or '' if no key is present. Endpoint code is
 * responsible for deciding whether absence of a key is acceptable (some
 * endpoints want to fall through to pi_devices auth, others want a 401).
 */
function getApiKeyHeader(): string {
    $api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
    if (empty($api_key)) {
        $auth_header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
        if (stripos($auth_header, 'Bearer ') === 0) {
            $api_key = substr($auth_header, 7);
        }
    }
    return (string)$api_key;
}

/**
 * Authenticate a non-Pi caller against the consumer_keys table.
 *
 * Used by endpoints that should be reachable from analytics consumers
 * (brain, investigator, monitoring dashboards) without granting them a
 * Pi-device key. See web-portal/database/schema_consumer_keys.sql.
 *
 * On success: returns ['id', 'name', 'permissions' => [...]] and updates
 * last_used_at as a fire-and-forget side effect.
 *
 * On failure: sends an HTTP error response and exits — never returns.
 *   - 401 if no key is present or the key is unknown / inactive
 *   - 403 if the key is valid but lacks $required_permission
 *
 * Endpoints that ALSO want to accept legacy Pi-device keys (during the
 * transition window) should try this function first inside a try/catch
 * shim, or refactor to call a new combined helper. Both options are
 * easy add-ons; this function intentionally does ONE thing.
 *
 * @param PDO    $pdo                 active database connection
 * @param string $required_permission a string from the permissions JSON,
 *                                    e.g. "read_chunks"
 * @return array<string,mixed>        on success
 */
function authenticateConsumerKey(PDO $pdo, string $required_permission): array {
    $api_key = getApiKeyHeader();
    if ($api_key === '') {
        errorResponse('Missing API key', 401);
    }

    $stmt = $pdo->prepare(
        "SELECT id, name, permissions
         FROM consumer_keys
         WHERE api_key = ? AND is_active = 1"
    );
    $stmt->execute([$api_key]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$row) {
        errorResponse('Invalid API key', 401);
    }

    $perms_raw = $row['permissions'] ?? '[]';
    $perms = is_string($perms_raw) ? (json_decode($perms_raw, true) ?: []) : (array)$perms_raw;
    if (!in_array($required_permission, $perms, true)) {
        errorResponse('Consumer key lacks permission: ' . $required_permission, 403);
    }

    // Touch last_used_at — fire-and-forget so a write failure doesn't deny the request.
    try {
        $pdo->prepare("UPDATE consumer_keys SET last_used_at = NOW() WHERE id = ?")
            ->execute([(int)$row['id']]);
    } catch (Throwable $e) {
        // Intentionally swallowed — the caller is already authenticated.
    }

    return [
        'id'          => (int)$row['id'],
        'name'        => $row['name'],
        'permissions' => $perms,
    ];
}
