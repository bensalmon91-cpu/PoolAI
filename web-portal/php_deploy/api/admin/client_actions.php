<?php
/**
 * PoolAIssistant Admin API - Client Actions
 *
 * Handles AJAX requests for client management:
 * - POST /api/admin/clients/{id}/suspend
 * - POST /api/admin/clients/{id}/activate
 * - POST /api/admin/clients/{id}/comp
 * - POST /api/admin/clients/{id}/extend
 * - DELETE /api/admin/clients/{id}
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/AdminClients.php';

header('Content-Type: application/json');

// Require admin auth
if (!isAdminLoggedIn()) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
    exit;
}

// Parse the request
$method = $_SERVER['REQUEST_METHOD'];
$path = $_SERVER['PATH_INFO'] ?? '';

// Extract client ID and action from path
// Expected format: /api/admin/clients/{id}/{action}
$parts = array_filter(explode('/', $path));
$parts = array_values($parts);

$clientId = intval($parts[0] ?? 0);
$action = $parts[1] ?? '';

if (!$clientId) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Client ID required']);
    exit;
}

$adminClients = new AdminClients();

// Verify client exists
$client = $adminClients->getClient($clientId);
if (!$client) {
    http_response_code(404);
    echo json_encode(['ok' => false, 'error' => 'Client not found']);
    exit;
}

// Parse JSON body if present
$input = json_decode(file_get_contents('php://input'), true) ?: [];

// Handle actions
try {
    switch ($action) {
        case 'suspend':
            if ($method !== 'POST') {
                throw new Exception('Method not allowed', 405);
            }
            $reason = trim($input['reason'] ?? '');
            if ($adminClients->suspendClient($clientId, $reason)) {
                echo json_encode(['ok' => true, 'message' => 'Client suspended']);
            } else {
                throw new Exception('Failed to suspend client');
            }
            break;

        case 'activate':
            if ($method !== 'POST') {
                throw new Exception('Method not allowed', 405);
            }
            if ($adminClients->activateClient($clientId)) {
                echo json_encode(['ok' => true, 'message' => 'Client activated']);
            } else {
                throw new Exception('Failed to activate client');
            }
            break;

        case 'comp':
            if ($method !== 'POST') {
                throw new Exception('Method not allowed', 405);
            }
            $reason = trim($input['reason'] ?? '');
            if ($adminClients->compAccount($clientId, $reason)) {
                echo json_encode(['ok' => true, 'message' => 'Client comped']);
            } else {
                throw new Exception('Failed to comp client');
            }
            break;

        case 'extend':
            if ($method !== 'POST') {
                throw new Exception('Method not allowed', 405);
            }
            $days = intval($input['days'] ?? 30);
            if ($days < 1 || $days > 365) {
                throw new Exception('Days must be between 1 and 365');
            }
            if ($adminClients->extendTrial($clientId, $days)) {
                echo json_encode(['ok' => true, 'message' => "Trial extended by $days days"]);
            } else {
                throw new Exception('Failed to extend trial');
            }
            break;

        case 'remove-override':
            if ($method !== 'POST') {
                throw new Exception('Method not allowed', 405);
            }
            if ($adminClients->removeOverride($clientId)) {
                echo json_encode(['ok' => true, 'message' => 'Override removed']);
            } else {
                throw new Exception('Failed to remove override');
            }
            break;

        case '':
            // Delete client (when action is empty and method is DELETE)
            if ($method === 'DELETE') {
                if ($adminClients->deleteClient($clientId)) {
                    echo json_encode(['ok' => true, 'message' => 'Client deleted']);
                } else {
                    throw new Exception('Failed to delete client');
                }
            } else {
                // Get client details
                echo json_encode(['ok' => true, 'client' => $client]);
            }
            break;

        default:
            http_response_code(400);
            echo json_encode(['ok' => false, 'error' => 'Unknown action: ' . $action]);
    }
} catch (Exception $e) {
    $code = $e->getCode() ?: 500;
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
}
