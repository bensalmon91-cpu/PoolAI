<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

header('Content-Type: text/plain');

echo "Testing devices query...\n\n";

require_once __DIR__ . '/../config/database.php';

try {
    $pdo = db();
    echo "Database connected OK\n";

    // Test basic query
    $result = $pdo->query('SELECT COUNT(*) as cnt FROM pi_devices')->fetch();
    echo "Device count: {$result['cnt']}\n";

    // Test the full query
    $devices = $pdo->query('
        SELECT d.*,
               (SELECT COUNT(*) FROM uploads WHERE device_id = d.id) as upload_count,
               (SELECT COUNT(*) FROM upload_chunks WHERE device_id = d.id) as chunk_count,
               TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) as minutes_ago
        FROM pi_devices d
        ORDER BY d.created_at DESC
    ')->fetchAll();

    echo "Query OK - found " . count($devices) . " devices\n\n";

    foreach ($devices as $d) {
        echo "- {$d['name']}: {$d['chunk_count']} chunks\n";
    }

} catch (Exception $e) {
    echo "ERROR: " . $e->getMessage() . "\n";
    echo "Trace: " . $e->getTraceAsString() . "\n";
}

@unlink(__FILE__);
