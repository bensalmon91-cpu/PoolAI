<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
header('Content-Type: text/plain');

echo "PHP Version: " . phpversion() . "\n\n";

// Test loading the file directly
$file = __DIR__ . '/../../includes/MobileDevices.php';
echo "Loading file: $file\n";
echo "File exists: " . (file_exists($file) ? 'YES' : 'NO') . "\n";
echo "File size: " . filesize($file) . " bytes\n\n";

echo "File contents:\n";
echo "---\n";
echo file_get_contents($file);
echo "\n---\n\n";

// Try to clear opcache
if (function_exists('opcache_invalidate')) {
    opcache_invalidate($file, true);
    echo "OPcache invalidated for file\n";
}

if (function_exists('opcache_reset')) {
    opcache_reset();
    echo "OPcache reset\n";
}

echo "\nNow trying require:\n";
try {
    require_once $file;
    echo "SUCCESS - MobileDevices loaded!\n";
    $md = new MobileDevices(1);
    echo "MobileDevices instance created!\n";
} catch (Throwable $e) {
    echo "ERROR: " . $e->getMessage() . "\n";
    echo "File: " . $e->getFile() . "\n";
    echo "Line: " . $e->getLine() . "\n";
}
