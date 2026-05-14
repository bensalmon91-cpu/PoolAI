<?php
/**
 * Clear Device Issues API
 * Clears has_issues flag on latest device health record
 * Requires admin session authentication
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/AuditLog.php';

header('Content-Type: application/json');

$auditFail = function(string $result, string $reason, int $deviceId = 0, array $extra = []) {
    AuditLog::record(
        'admin',
        'device.issues_clear',
        ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
        $deviceId > 0 ? ['type' => 'device', 'id' => (string)$deviceId] : null,
        $result,
        array_merge(['reason' => $reason], $extra)
    );
};

// Require admin login (uses startSecureSession with correct session name)
if (!isAdmin()) {
    $auditFail('denied', 'not_authenticated');
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    $auditFail('denied', 'method_not_allowed');
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

$input = json_decode(file_get_contents('php://input'), true);
$device_id = isset($input['device_id']) ? (int)$input['device_id'] : 0;

if (!$device_id) {
    $auditFail('denied', 'invalid_device_id');
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'device_id required']);
    exit;
}

try {
    $pdo = db();

    // Verify device exists
    $stmt = $pdo->prepare("SELECT id FROM pi_devices WHERE id = ? AND is_active = 1");
    $stmt->execute([$device_id]);
    if (!$stmt->fetch()) {
        $auditFail('denied', 'device_not_found', $device_id);
        http_response_code(404);
        echo json_encode(['ok' => false, 'error' => 'Device not found']);
        exit;
    }

    // Clear issues on the most recent health record
    $stmt = $pdo->prepare("
        UPDATE device_health
        SET has_issues = 0, issues_json = NULL
        WHERE device_id = ?
        ORDER BY ts DESC
        LIMIT 1
    ");
    $stmt->execute([$device_id]);

    AuditLog::record(
        'admin',
        'device.issues_clear',
        ['type' => 'admin', 'id' => $_SESSION['admin_username'] ?? null],
        ['type' => 'device', 'id' => (string)$device_id],
        'ok',
        ['rows_cleared' => $stmt->rowCount()]
    );

    echo json_encode(['ok' => true, 'cleared' => $stmt->rowCount()]);

} catch (PDOException $e) {
    $auditFail('fail', 'db_error', $device_id, ['error' => $e->getMessage()]);
    error_log("clear_device_issues DB error: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Database error']);
}
