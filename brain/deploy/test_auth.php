<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

header('Content-Type: text/plain');

echo "Testing auth includes...\n\n";

try {
    echo "1. Loading auth.php...\n";
    require_once __DIR__ . '/../includes/auth.php';
    echo "   OK\n";

    echo "2. Loading functions.php...\n";
    require_once __DIR__ . '/../includes/functions.php';
    echo "   OK\n";

    echo "3. Loading api_helpers.php...\n";
    require_once __DIR__ . '/../includes/api_helpers.php';
    echo "   OK\n";

    echo "4. Calling requireAuth()...\n";
    // This will redirect if not logged in
    // requireAuth();
    echo "   SKIPPED (would redirect)\n";

    echo "\nAll includes OK!\n";

} catch (Exception $e) {
    echo "ERROR: " . $e->getMessage() . "\n";
    echo "File: " . $e->getFile() . ":" . $e->getLine() . "\n";
}

@unlink(__FILE__);
