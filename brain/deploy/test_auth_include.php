<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

header('Content-Type: text/plain');
echo "Testing auth include...\n\n";

try {
    require_once __DIR__ . '/../includes/auth.php';
    echo "auth.php loaded OK\n";

    require_once __DIR__ . '/../includes/functions.php';
    echo "functions.php loaded OK\n";

    require_once __DIR__ . '/../includes/api_helpers.php';
    echo "api_helpers.php loaded OK\n";

    echo "\nAll includes successful!\n";
} catch (Throwable $e) {
    echo "ERROR: " . $e->getMessage() . "\n";
    echo "File: " . $e->getFile() . ":" . $e->getLine() . "\n";
    echo "Trace:\n" . $e->getTraceAsString() . "\n";
}

@unlink(__FILE__);
