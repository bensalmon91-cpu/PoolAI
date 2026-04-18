<?php
/**
 * Download Software Update
 *
 * Serves update files from the data/updates directory.
 * Usage:
 *   download.php?file=update-v6.8.9.tar.gz       - update tarball
 *   download.php?file=update-v6.8.9.tar.gz.sig   - detached Ed25519 signature
 *
 * Signatures are public (verifiability requires it); no auth gate needed.
 */

// Disable output buffering for large files
if (ob_get_level()) {
    ob_end_clean();
}

// Get the requested filename
$file = $_GET['file'] ?? '';

// Validate filename (prevent directory traversal)
if (empty($file) || preg_match('/[\/\\\\]/', $file) || strpos($file, '..') !== false) {
    http_response_code(400);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Invalid filename']);
    exit;
}

// Allow .tar.gz and .tar.gz.sig only. Everything else is 400.
$isSignature = false;
if (preg_match('/^update-v[\d.]+\.tar\.gz$/', $file)) {
    $isSignature = false;
} elseif (preg_match('/^update-v[\d.]+\.tar\.gz\.sig$/', $file)) {
    $isSignature = true;
} else {
    http_response_code(400);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Invalid file format']);
    exit;
}

// Path to updates directory (relative to document root)
$updates_dir = $_SERVER['DOCUMENT_ROOT'] . '/poolaissistant/data/updates/';
$filepath = $updates_dir . $file;

// Check if file exists
if (!file_exists($filepath)) {
    http_response_code(404);
    header('Content-Type: application/json');
    echo json_encode([
        'error' => 'File not found',
        'file' => $file,
        'debug_path' => $filepath
    ]);
    exit;
}

// Serve the file
$filesize = filesize($filepath);

header('Content-Type: ' . ($isSignature ? 'application/octet-stream' : 'application/gzip'));
header('Content-Disposition: attachment; filename="' . $file . '"');
header('Content-Length: ' . $filesize);
header('Cache-Control: no-cache, must-revalidate');
header('Pragma: no-cache');

// Stream the file
readfile($filepath);
exit;
