<?php
header('Content-Type: text/plain');
$auth_file = __DIR__ . '/../includes/auth.php';
echo "Auth file: $auth_file\n";
echo "Exists: " . (file_exists($auth_file) ? "YES" : "NO") . "\n";
if (file_exists($auth_file)) {
    echo "Size: " . filesize($auth_file) . " bytes\n";
    echo "First 500 chars:\n";
    echo substr(file_get_contents($auth_file), 0, 500) . "\n";
}
@unlink(__FILE__);
