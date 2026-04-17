<?php
/**
 * Install device status API files
 * Copies from poolai FTP location to poolaissistant server
 */
header('Content-Type: text/plain');

$src_base = '/home/u931726538/domains/poolai.modprojects.co.uk/public_html';
$dest_base = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant';

$files = [
    'api/health.php',
    'api/device_status.php',
    'api/migrate_device_status.php',
    'admin/devices.php'
];

echo "Installing device status files...\n\n";

$copied = 0;
foreach ($files as $file) {
    $src = "$src_base/$file";
    $dest = "$dest_base/$file";

    if (!file_exists($src)) {
        echo "SKIP: $file (source not found)\n";
        continue;
    }

    if (copy($src, $dest)) {
        echo "OK: $file (" . filesize($dest) . " bytes)\n";
        @unlink($src);
        $copied++;
    } else {
        echo "FAIL: $file\n";
    }
}

echo "\nCopied $copied files.\n";

// Run migration
echo "\nRunning database migration...\n";
require_once $dest_base . '/config/database.php';

try {
    $pdo = db();
    $columns = [
        "ALTER TABLE pi_devices ADD COLUMN last_test_status VARCHAR(20) DEFAULT NULL",
        "ALTER TABLE pi_devices ADD COLUMN last_test_results JSON DEFAULT NULL",
        "ALTER TABLE pi_devices ADD COLUMN last_test_at TIMESTAMP NULL DEFAULT NULL"
    ];

    foreach ($columns as $sql) {
        try {
            $pdo->exec($sql);
            echo "  Added column\n";
        } catch (PDOException $e) {
            if (strpos($e->getMessage(), 'Duplicate column') !== false) {
                echo "  Column exists (OK)\n";
            }
        }
    }
    echo "Migration complete!\n";
} catch (Exception $e) {
    echo "Migration error: " . $e->getMessage() . "\n";
}

// Cleanup
@unlink(__FILE__);
echo "\nInstaller removed.\n";
echo "Done!\n";
