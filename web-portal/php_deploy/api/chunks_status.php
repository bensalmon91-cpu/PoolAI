<?php
/**
 * Chunks Status API
 * Returns list of chunks already uploaded for a device
 * Pi uses this to know which chunks to skip
 *
 * GET /api/chunks_status.php
 * Headers: X-API-Key: <device-api-key>
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    errorResponse('Method not allowed', 405);
}

// Authenticate device
$api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (empty($api_key)) {
    errorResponse('Missing API key', 401);
}

$pdo = db();

// Verify API key and get device
$stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE api_key = ? AND is_active = 1");
$stmt->execute([$api_key]);
$device = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$device) {
    errorResponse('Invalid API key', 401);
}

// Get all uploaded chunks for this device
$stmt = $pdo->prepare("
    SELECT period_start, period_end, checksum, row_count, compressed_size, uploaded_at
    FROM upload_chunks
    WHERE device_id = ?
    ORDER BY period_start DESC
");
$stmt->execute([$device['id']]);
$chunks = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Build a lookup map for easy checking on Pi side
$chunk_map = [];
foreach ($chunks as $chunk) {
    $key = $chunk['period_start'] . '_' . $chunk['period_end'];
    $chunk_map[$key] = [
        'checksum' => $chunk['checksum'],
        'row_count' => (int)$chunk['row_count'],
        'uploaded_at' => $chunk['uploaded_at']
    ];
}

jsonResponse([
    'ok' => true,
    'device_name' => $device['name'],
    'chunk_count' => count($chunks),
    'chunks' => $chunk_map
]);
