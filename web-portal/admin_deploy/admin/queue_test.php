<?php
/**
 * Queue Test Questions - DELETE AFTER USE
 */
require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();
header('Content-Type: text/plain');

echo "=== Queue Test Questions ===\n\n";

// Get available devices
$devices = $pdo->query("SELECT id, name, device_uuid, last_seen FROM pi_devices WHERE is_active = 1")->fetchAll(PDO::FETCH_ASSOC);

echo "Available devices:\n";
foreach ($devices as $d) {
    $last_seen = $d['last_seen'] ? date('M j g:ia', strtotime($d['last_seen'])) : 'Never';
    echo "  ID {$d['id']}: {$d['name']} (UUID: " . substr($d['device_uuid'], 0, 8) . "...) - Last seen: $last_seen\n";
}

// Get a test question
$question = $pdo->query("SELECT id, text FROM ai_questions WHERE is_active = 1 ORDER BY id LIMIT 1")->fetch(PDO::FETCH_ASSOC);

if (!$question) {
    echo "\nERROR: No questions found in database!\n";
    exit;
}

echo "\nTest question: {$question['text']}\n";

// Queue to first active device
if (!empty($_GET['device_id'])) {
    $device_id = (int)$_GET['device_id'];
} else {
    $device_id = $devices[0]['id'] ?? null;
}

if (!$device_id) {
    echo "\nERROR: No device selected!\n";
    echo "Add ?device_id=X to the URL to select a device.\n";
    exit;
}

echo "\nQueueing to device ID: $device_id\n";

// Check for existing pending question for this device
$existing = $pdo->prepare("SELECT id FROM ai_question_queue WHERE device_id = ? AND question_id = ? AND status = 'pending'");
$existing->execute([$device_id, $question['id']]);
if ($existing->fetch()) {
    echo "\nQuestion already queued for this device (pending).\n";
    echo "Delete it first or wait for it to be delivered.\n";
    exit;
}

// Queue the question
$stmt = $pdo->prepare("
    INSERT INTO ai_question_queue (device_id, question_id, pool, triggered_by, status, expires_at)
    VALUES (?, ?, '', 'manual_test', 'pending', DATE_ADD(NOW(), INTERVAL 24 HOUR))
");
$stmt->execute([$device_id, $question['id']]);
$queue_id = $pdo->lastInsertId();

echo "SUCCESS! Question queued with ID: $queue_id\n";
echo "\nThe question will be delivered on the next heartbeat from device $device_id.\n";
echo "Watch the heartbeat response to see it being delivered.\n";

// Show current queue
echo "\n=== Current Queue ===\n";
$queue = $pdo->query("
    SELECT qq.id, qq.device_id, d.name as device_name, q.text as question_text, qq.status, qq.created_at
    FROM ai_question_queue qq
    JOIN ai_questions q ON qq.question_id = q.id
    JOIN pi_devices d ON qq.device_id = d.id
    WHERE qq.status IN ('pending', 'delivered')
    ORDER BY qq.created_at DESC
    LIMIT 10
")->fetchAll(PDO::FETCH_ASSOC);

foreach ($queue as $q) {
    echo "  #{$q['id']}: {$q['device_name']} - " . substr($q['question_text'], 0, 40) . "... [{$q['status']}]\n";
}
