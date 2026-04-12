<?php
/**
 * Check for Software Updates API
 *
 * Returns information about available updates for Pi devices.
 * Usage: check_updates.php?version=6.9.30
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

require_once __DIR__ . '/../config/database.php';

// Get current version from request
$current_version = $_GET['version'] ?? '0.0.0';

// Sanitize version string
$current_version = preg_replace('/[^0-9.]/', '', $current_version);

try {
    $pdo = db();

    // Get the latest active update
    $stmt = $pdo->query("SELECT version, filename, file_size, checksum, description, created_at
                         FROM software_updates
                         WHERE is_active = 1
                         ORDER BY created_at DESC
                         LIMIT 1");
    $latest = $stmt->fetch();

    if (!$latest) {
        // No updates in database
        echo json_encode([
            'update_available' => false,
            'current_version' => $current_version,
            'message' => 'No updates available'
        ]);
        exit;
    }

    // Compare versions
    $latest_version = $latest['version'];

    // Use version_compare for proper semantic versioning
    if (version_compare($latest_version, $current_version, '>')) {
        echo json_encode([
            'update_available' => true,
            'current_version' => $current_version,
            'version' => $latest_version,
            'filename' => $latest['filename'],
            'file_size' => (int)$latest['file_size'],
            'checksum' => $latest['checksum'],
            'description' => $latest['description'],
            'download_url' => '/api/updates/download.php?file=' . urlencode($latest['filename'])
        ]);
    } else {
        echo json_encode([
            'update_available' => false,
            'current_version' => $current_version,
            'latest_version' => $latest_version,
            'message' => 'You are running the latest version'
        ]);
    }

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode([
        'error' => 'Database error',
        'message' => $e->getMessage()
    ]);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'error' => 'Server error',
        'message' => $e->getMessage()
    ]);
}
