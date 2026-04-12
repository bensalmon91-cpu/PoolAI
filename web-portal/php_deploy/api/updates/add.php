<?php
/**
 * Add Software Update to Database
 *
 * Usage: add.php?version=6.6.9&filename=update-v6.6.9.tar.gz&size=123456&checksum=abc123&description=...
 *
 * Security: This endpoint should be protected or removed after use.
 */

require_once __DIR__ . '/../../config/database.php';

header('Content-Type: application/json');

// Get parameters
$version = $_GET['version'] ?? '';
$filename = $_GET['filename'] ?? '';
$size = intval($_GET['size'] ?? 0);
$checksum = $_GET['checksum'] ?? '';
$description = $_GET['description'] ?? '';

// Validate required fields
if (empty($version) || empty($filename) || $size <= 0 || empty($checksum)) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing required fields: version, filename, size, checksum']);
    exit;
}

try {
    $pdo = db();

    // Check if version already exists
    $stmt = $pdo->prepare("SELECT id FROM software_updates WHERE version = ?");
    $stmt->execute([$version]);

    if ($stmt->fetch()) {
        // Update existing
        $stmt = $pdo->prepare("UPDATE software_updates SET filename = ?, file_size = ?, checksum = ?, description = ?, is_active = 1, created_at = NOW() WHERE version = ?");
        $stmt->execute([$filename, $size, $checksum, $description, $version]);
        echo json_encode(['success' => true, 'action' => 'updated', 'version' => $version]);
    } else {
        // Insert new
        $stmt = $pdo->prepare("INSERT INTO software_updates (version, filename, file_size, checksum, description, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, NOW())");
        $stmt->execute([$version, $filename, $size, $checksum, $description]);
        echo json_encode(['success' => true, 'action' => 'created', 'version' => $version, 'id' => $pdo->lastInsertId()]);
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Database error: ' . $e->getMessage()]);
}
