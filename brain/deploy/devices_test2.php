<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
header('Content-Type: text/plain');

echo "Step 1: Include auth.php\n";
require_once __DIR__ . '/../includes/auth.php';
echo "OK\n";

echo "Step 2: Include functions.php\n";
require_once __DIR__ . '/../includes/functions.php';
echo "OK\n";

echo "Step 3: Call requireAuth()\n";
// requireAuth(); // Skip - will redirect
echo "SKIPPED\n";

echo "Step 4: Get database\n";
$pdo = db();
echo "OK\n";

echo "Step 5: Run query\n";
$devices = $pdo->query('
    SELECT d.*,
           (SELECT COUNT(*) FROM uploads WHERE device_id = d.id) as upload_count,
           TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) as minutes_ago
    FROM pi_devices d
    ORDER BY d.created_at DESC
')->fetchAll();
echo "OK - " . count($devices) . " devices\n";

echo "\nAll steps passed!\n";
@unlink(__FILE__);
