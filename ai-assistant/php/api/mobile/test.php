<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
header('Content-Type: text/plain');

echo "PHP Version: " . phpversion() . "\n\n";

$file = __DIR__ . '/../../includes/MobileDevices.php';
echo "File path: $file\n";
echo "File exists: " . (file_exists($file) ? 'YES' : 'NO') . "\n";
echo "File size: " . filesize($file) . " bytes\n\n";

echo "=== FILE CONTENTS ===\n";
readfile($file);
echo "\n=== END CONTENTS ===\n\n";

if (function_exists('opcache_invalidate')) {
    opcache_invalidate($file, true);
    echo "OPcache invalidated\n";
}

echo "\nTrying require:\n";
try {
    require_once $file;
    echo "SUCCESS - MobileDevices loaded!\n";
    $md = new MobileDevices(1);
    echo "Instance created: " . get_class($md) . "\n";
} catch (Throwable $e) {
    echo "ERROR: " . $e->getMessage() . "\n";
    echo "In file: " . $e->getFile() . "\n";
    echo "At line: " . $e->getLine() . "\n";
}
