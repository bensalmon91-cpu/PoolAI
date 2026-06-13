<?php
/**
 * Software Update Check API
 *
 * Public endpoint - no API key required. Returns the active software_updates
 * row when it is newer than the Pi's reported current_version. This is THE Pi
 * update path (scripts/update_check.py hits /api/updates/check.php).
 *
 * GET /api/updates/check.php?current_version=X.Y.Z
 */

require_once __DIR__ . '/../../config/database.php';

header('Content-Type: application/json');

$current_version = $_GET['current_version'] ?? '0.0.0';

try {
    $pdo = db();

    $stmt = $pdo->query("SELECT version, filename, file_size, checksum, description
                         FROM software_updates
                         WHERE is_active = 1
                         ORDER BY created_at DESC
                         LIMIT 1");
    $latest = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$latest) {
        echo json_encode([
            'update_available' => false,
            'latest_version' => $current_version,
            'message' => 'No updates available'
        ]);
        exit;
    }

    if (version_compare($latest['version'], $current_version, '>')) {
        echo json_encode([
            'update_available' => true,
            'version' => $latest['version'],
            'download_url' => '/api/updates/download.php?file=' . urlencode($latest['filename']),
            'checksum' => $latest['checksum'],
            'file_size' => (int)$latest['file_size'],
            'description' => $latest['description']
        ]);
    } else {
        echo json_encode([
            'update_available' => false,
            'latest_version' => $latest['version'],
            'message' => 'Already up to date'
        ]);
    }

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Server error']);
}
