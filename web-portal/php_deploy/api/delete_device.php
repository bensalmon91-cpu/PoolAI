<?php
/**
 * Delete Device API
 * Soft-deletes a device (sets is_active = 0)
 * Device can re-register if it sends another heartbeat
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

header('Content-Type: application/json');

// Require admin login (uses startSecureSession with correct session name)
if (!isAdmin()) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

$input = json_decode(file_get_contents('php://input'), true);
$device_id = isset($input['device_id']) ? (int)$input['device_id'] : 0;

if (!$device_id) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'device_id required']);
    exit;
}

try {
    $pdo = db();

    // Soft delete - set is_active = 0
    $stmt = $pdo->prepare("UPDATE pi_devices SET is_active = 0 WHERE id = ?");
    $stmt->execute([$device_id]);

    if ($stmt->rowCount() > 0) {
        echo json_encode(['ok' => true, 'deleted' => true]);
    } else {
        echo json_encode(['ok' => false, 'error' => 'Device not found']);
    }

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Database error']);
}
