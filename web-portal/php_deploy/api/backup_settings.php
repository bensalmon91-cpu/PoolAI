<?php
// Copyright Ben Salmon 2026. All Rights Reserved.
// PoolAIssistant - Settings Backup API

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/api_helpers.php';

// Only accept POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('Method not allowed', 405);
}

// Validate API key
$api_key = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (!$api_key) {
    errorResponse('API key required', 401);
}

$pdo = db();

// Get device by API key
$stmt = $pdo->prepare("SELECT id, name FROM pi_devices WHERE api_key = ? AND is_active = 1");
$stmt->execute([$api_key]);
$device = $stmt->fetch();

if (!$device) {
    errorResponse('Invalid API key', 401);
}

$device_id = $device['id'];

// Get JSON payload
$input = file_get_contents('php://input');
$data = json_decode($input, true);

if (!$data) {
    errorResponse('Invalid JSON payload');
}

// Create backups directory
$backup_dir = __DIR__ . '/../data/backups/' . $device_id;
if (!is_dir($backup_dir)) {
    mkdir($backup_dir, 0755, true);
}

// Save backup file with timestamp
$timestamp = date('Y-m-d_His');
$backup_file = $backup_dir . "/settings_{$timestamp}.json";

if (!file_put_contents($backup_file, json_encode($data, JSON_PRETTY_PRINT))) {
    errorResponse('Failed to save backup');
}

// Update device last_seen
$stmt = $pdo->prepare("UPDATE pi_devices SET last_seen = NOW() WHERE id = ?");
$stmt->execute([$device_id]);

// Log activity
$stmt = $pdo->prepare("INSERT INTO device_activity_log (device_id, action, ip_address) VALUES (?, 'backup', ?)");
$stmt->execute([$device_id, $_SERVER['REMOTE_ADDR'] ?? '']);

// Keep only last 30 backups per device
$backups = glob($backup_dir . '/settings_*.json');
if (count($backups) > 30) {
    usort($backups, function($a, $b) {
        return filemtime($a) - filemtime($b);
    });
    $to_delete = array_slice($backups, 0, count($backups) - 30);
    foreach ($to_delete as $old) {
        unlink($old);
    }
}

jsonResponse([
    'ok' => true,
    'message' => 'Settings backed up successfully',
    'backup_count' => min(count($backups), 30)
]);
