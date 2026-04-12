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
