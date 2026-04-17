<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/functions.php';

requireAuth();

$pdo = db();
$devices = $pdo->query('
    SELECT d.*,
           (SELECT COUNT(*) FROM uploads WHERE device_id = d.id) as upload_count,
           TIMESTAMPDIFF(MINUTE, d.last_seen, NOW()) as minutes_ago
    FROM pi_devices d
    ORDER BY d.created_at DESC
')->fetchAll();
?>
<!DOCTYPE html>
<html>
<head><title>Devices - Minimal Test</title></head>
<body>
<h1>Devices (<?php echo count($devices); ?>)</h1>
<ul>
<?php foreach ($devices as $d): ?>
<li><?php echo htmlspecialchars($d['name']); ?> - <?php echo $d['upload_count']; ?> uploads</li>
<?php endforeach; ?>
</ul>
</body>
</html>
