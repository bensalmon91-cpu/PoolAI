<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
header('Content-Type: text/plain');

echo "Testing requireAuth()...\n\n";

require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/functions.php';

echo "1. initSession()...\n";
try {
    initSession();
    echo "   OK\n";
} catch (Throwable $e) {
    echo "   FAIL: " . $e->getMessage() . "\n";
}

echo "2. isLoggedIn()...\n";
try {
    $logged = isLoggedIn();
    echo "   Result: " . ($logged ? "TRUE" : "FALSE") . "\n";
} catch (Throwable $e) {
    echo "   FAIL: " . $e->getMessage() . "\n";
}

echo "3. requireAuth() (will redirect if not logged in)...\n";
echo "   SKIPPING - would exit\n";

echo "\nDone!\n";
@unlink(__FILE__);
