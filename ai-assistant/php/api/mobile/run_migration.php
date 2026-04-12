<?php
/**
 * Temporary migration script - DELETE AFTER USE
 */

header('Content-Type: text/plain');

require_once __DIR__ . '/../../config/database.php';
// Alternative path
if (!function_exists('db')) {
    require_once dirname(dirname(__DIR__)) . '/config/database.php';
}

$pdo = db();

// Read and execute the migration SQL
// Path: api/mobile -> api -> root -> database
$sqlFile = __DIR__ . '/../../database/schema_mobile.sql';
// Try alternate paths if not found
if (!file_exists($sqlFile)) {
    $sqlFile = dirname(dirname(__DIR__)) . '/database/schema_mobile.sql';
}
if (!file_exists($sqlFile)) {
    $sqlFile = '/home/u931726538/public_html/poolaissistant/database/schema_mobile.sql';
}

if (!file_exists($sqlFile)) {
    die("Migration file not found: $sqlFile\n");
}

$sql = file_get_contents($sqlFile);

// Split by semicolons but handle DELIMITER changes for procedures
$statements = [];
$current = '';
$delimiter = ';';

$lines = explode("\n", $sql);
foreach ($lines as $line) {
    $trimmed = trim($line);

    // Skip comments
    if (strpos($trimmed, '--') === 0 || strpos($trimmed, '#') === 0) {
        continue;
    }

    // Handle DELIMITER changes
    if (preg_match('/^DELIMITER\s+(.+)$/i', $trimmed, $matches)) {
        $delimiter = trim($matches[1]);
        continue;
    }

    $current .= $line . "\n";

    // Check for delimiter at end of line
    if (substr(rtrim($current), -strlen($delimiter)) === $delimiter) {
        $stmt = substr(rtrim($current), 0, -strlen($delimiter));
        $stmt = trim($stmt);
        if (!empty($stmt)) {
            $statements[] = $stmt;
        }
        $current = '';
    }
}

// Execute each statement
$success = 0;
$errors = [];

foreach ($statements as $i => $stmt) {
    if (empty(trim($stmt))) continue;

    try {
        $pdo->exec($stmt);
        $success++;

        // Show what was executed
        $preview = substr($stmt, 0, 60);
        $preview = preg_replace('/\s+/', ' ', $preview);
        echo "OK: $preview...\n";
    } catch (PDOException $e) {
        $preview = substr($stmt, 0, 60);
        $preview = preg_replace('/\s+/', ' ', $preview);

        // Ignore "already exists" errors
        if (strpos($e->getMessage(), 'already exists') !== false ||
            strpos($e->getMessage(), 'Duplicate') !== false) {
            echo "SKIP (exists): $preview...\n";
            $success++;
        } else {
            $errors[] = "ERROR: $preview... - " . $e->getMessage();
            echo "ERROR: $preview... - " . $e->getMessage() . "\n";
        }
    }
}

echo "\n=== MIGRATION COMPLETE ===\n";
echo "Successful: $success\n";
echo "Errors: " . count($errors) . "\n";

if (count($errors) > 0) {
    echo "\nError details:\n";
    foreach ($errors as $err) {
        echo "- $err\n";
    }
}

// Verify tables exist
echo "\n=== VERIFYING TABLES ===\n";
$tables = ['mobile_tokens', 'push_tokens', 'push_notifications', 'user_notification_prefs', 'device_link_codes'];

foreach ($tables as $table) {
    try {
        $result = $pdo->query("SHOW TABLES LIKE '$table'")->fetch();
        if ($result) {
            echo "OK: $table exists\n";
        } else {
            echo "MISSING: $table\n";
        }
    } catch (PDOException $e) {
        echo "ERROR checking $table: " . $e->getMessage() . "\n";
    }
}

echo "\n=== DELETE THIS FILE AFTER VERIFYING ===\n";
