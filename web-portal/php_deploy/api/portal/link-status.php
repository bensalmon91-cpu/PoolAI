<?php
/**
 * Check Device Link Status API
 * Called by Pi devices to check if they are linked to a user account
 *
 * GET /api/portal/link-status.php
 * Headers: X-API-Key: <device_api_key>
 * Returns: { "linked": true/false, "account_name": "...", "linked_at": "..." }
 */

require_once __DIR__ . '/../../config/config.php';
require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
header('Content-Type: application/json');

// Authenticate device
$device = authenticateDevice();
if (!$device) {
    http_response_code(401);
    echo json_encode(['linked' => false, 'error' => 'Invalid API key']);
    exit;
}

$pdo = db();

try {
    // Check if device is linked to any user account
    $stmt = $pdo->prepare("
        SELECT u.id, u.email, u.name, ud.role, ud.linked_at
        FROM user_devices ud
        JOIN portal_users u ON ud.user_id = u.id
        WHERE ud.device_id = ?
        ORDER BY ud.linked_at ASC
        LIMIT 1
    ");
    $stmt->execute([$device['id']]);
    $link = $stmt->fetch();

    if ($link) {
        echo json_encode([
            'linked' => true,
            'account_name' => $link['name'] ?: $link['email'],
            'account_email' => $link['email'],
            'role' => $link['role'],
            'linked_at' => $link['linked_at']
        ]);
    } else {
        echo json_encode([
            'linked' => false,
            'reason' => 'not_linked'
        ]);
    }

} catch (PDOException $e) {
    error_log("Link status error: " . $e->getMessage());
    http_response_code(500);
    echo json_encode([
        'linked' => false,
        'error' => 'Database error'
    ]);
}
