<?php
/**
 * Chunked Upload API Endpoint
 * Accepts compressed time-period chunks from Pi devices
 *
 * POST /api/upload_chunk.php
 * Headers: X-API-Key: <device-api-key>
 * Body: multipart/form-data with:
 *   - file: the .db.gz compressed chunk
 *   - period_start: YYYY-MM-DD
 *   - period_end: YYYY-MM-DD
 *   - row_count: number of rows in chunk
 *   - original_size: uncompressed size in bytes
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

// Set generous limits for chunk uploads (chunks should be <100MB compressed)
ini_set('upload_max_filesize', '200M');
ini_set('post_max_size', '210M');
ini_set('max_execution_time', '300');
ini_set('memory_limit', '256M');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
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

$device_id = $device['id'];

// Validate required fields
$period_start = $_POST['period_start'] ?? '';
$period_end = $_POST['period_end'] ?? '';
$row_count = intval($_POST['row_count'] ?? 0);
$original_size = intval($_POST['original_size'] ?? 0);

if (empty($period_start) || empty($period_end)) {
    errorResponse('Missing period_start or period_end');
}

// Validate date format
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $period_start) ||
    !preg_match('/^\d{4}-\d{2}-\d{2}$/', $period_end)) {
    errorResponse('Invalid date format. Use YYYY-MM-DD');
}

// Check file upload
if (!isset($_FILES['file']) || $_FILES['file']['error'] !== UPLOAD_ERR_OK) {
    $error_messages = [
        UPLOAD_ERR_INI_SIZE => 'File exceeds server limit',
        UPLOAD_ERR_FORM_SIZE => 'File exceeds form limit',
        UPLOAD_ERR_PARTIAL => 'File only partially uploaded',
        UPLOAD_ERR_NO_FILE => 'No file uploaded',
        UPLOAD_ERR_NO_TMP_DIR => 'Server temp directory missing',
        UPLOAD_ERR_CANT_WRITE => 'Failed to write file',
        UPLOAD_ERR_EXTENSION => 'Upload blocked by extension',
    ];
    $error_code = $_FILES['file']['error'] ?? UPLOAD_ERR_NO_FILE;
    $error_msg = $error_messages[$error_code] ?? 'Unknown upload error';
    errorResponse($error_msg, 400);
}

$uploaded_file = $_FILES['file']['tmp_name'];
$original_filename = $_FILES['file']['name'];
$compressed_size = $_FILES['file']['size'];

// Validate file extension
if (!preg_match('/\.(gz|zip)$/i', $original_filename)) {
    errorResponse('File must be .gz or .zip compressed');
}

// Calculate checksum
$checksum = hash_file('sha256', $uploaded_file);

// Check if this chunk already exists
$stmt = $pdo->prepare("
    SELECT id, checksum FROM upload_chunks
    WHERE device_id = ? AND period_start = ? AND period_end = ?
");
$stmt->execute([$device_id, $period_start, $period_end]);
$existing = $stmt->fetch(PDO::FETCH_ASSOC);

if ($existing) {
    if ($existing['checksum'] === $checksum) {
        // Same chunk, skip
        jsonResponse([
            'ok' => true,
            'skipped' => true,
            'message' => 'Chunk already uploaded with same checksum'
        ]);
    }
    // Different checksum - will update
}

// Create storage directory structure: /data/chunks/{device_id}/
$chunks_dir = __DIR__ . '/../data/chunks/' . $device_id;
if (!is_dir($chunks_dir)) {
    mkdir($chunks_dir, 0755, true);
}

// Generate stored filename
$stored_filename = sprintf('%s_to_%s_%s.db.gz',
    $period_start,
    $period_end,
    substr($checksum, 0, 8)
);
$stored_path = $chunks_dir . '/' . $stored_filename;

// Move uploaded file
if (!move_uploaded_file($uploaded_file, $stored_path)) {
    errorResponse('Failed to store file', 500);
}

try {
    if ($existing) {
        // Update existing chunk
        // Delete old file if different
        $old_stmt = $pdo->prepare("SELECT chunk_filename FROM upload_chunks WHERE id = ?");
        $old_stmt->execute([$existing['id']]);
        $old_filename = $old_stmt->fetchColumn();
        if ($old_filename && $old_filename !== $stored_filename) {
            $old_path = $chunks_dir . '/' . $old_filename;
            if (file_exists($old_path)) {
                unlink($old_path);
            }
        }

        $stmt = $pdo->prepare("
            UPDATE upload_chunks SET
                chunk_filename = ?,
                file_size = ?,
                compressed_size = ?,
                row_count = ?,
                checksum = ?,
                uploaded_at = NOW()
            WHERE id = ?
        ");
        $stmt->execute([
            $stored_filename,
            $original_size,
            $compressed_size,
            $row_count,
            $checksum,
            $existing['id']
        ]);
        $chunk_id = $existing['id'];
    } else {
        // Insert new chunk
        $stmt = $pdo->prepare("
            INSERT INTO upload_chunks
            (device_id, chunk_filename, period_start, period_end, file_size, compressed_size, row_count, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ");
        $stmt->execute([
            $device_id,
            $stored_filename,
            $period_start,
            $period_end,
            $original_size,
            $compressed_size,
            $row_count,
            $checksum
        ]);
        $chunk_id = $pdo->lastInsertId();
    }

    // Log activity
    $stmt = $pdo->prepare("
        INSERT INTO device_activity_log (device_id, action, ip_address, details)
        VALUES (?, 'upload', ?, ?)
    ");
    $details = json_encode([
        'type' => 'chunk',
        'period' => "$period_start to $period_end",
        'rows' => $row_count,
        'size' => $compressed_size
    ]);
    $stmt->execute([$device_id, $_SERVER['REMOTE_ADDR'] ?? '', $details]);

    // Update device last_seen
    $stmt = $pdo->prepare("UPDATE pi_devices SET last_seen = NOW() WHERE id = ?");
    $stmt->execute([$device_id]);

    jsonResponse([
        'ok' => true,
        'chunk_id' => $chunk_id,
        'period' => "$period_start to $period_end",
        'compressed_size' => $compressed_size,
        'checksum' => $checksum
    ]);

} catch (PDOException $e) {
    // Clean up file on error
    if (file_exists($stored_path)) {
        unlink($stored_path);
    }
    errorResponse('Database error: ' . $e->getMessage(), 500);
}
