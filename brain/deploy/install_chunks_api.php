<?php
/**
 * Chunks API Installer for PoolAIssistant
 *
 * Copies the chunks API files from poolai.modprojects.co.uk
 * to poolaissistant.modprojects.co.uk
 *
 * Run via: https://poolai.modprojects.co.uk/install_chunks_api.php
 * DELETE THIS FILE AFTER RUNNING
 */

header('Content-Type: text/plain');

// Correct paths based on server structure
$ftp_base = '/home/u931726538/domains/poolai.modprojects.co.uk/public_html';
$correct_base = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant';

echo "==============================================\n";
echo "PoolAIssistant Chunks API Installer\n";
echo "==============================================\n\n";

// Verify we can access both locations
echo "Verifying paths...\n";
echo "  Source (poolai): $ftp_base\n";
echo "  Target (poolaissistant): $correct_base\n\n";

$test_file = $correct_base . '/config/database.php';
if (!file_exists($test_file)) {
    echo "ERROR: Cannot find target database.php at $test_file\n";
    exit(1);
}
echo "OK - Target location verified\n\n";

// Files to copy
$files_to_copy = [
    'api/list_chunks.php',
    'api/upload_chunk.php',
    'api/download_chunks.php',
    'api/chunks_status.php',
    'includes/api_helpers.php',
];

echo "Copying API files...\n";

$copied = 0;
$failed = 0;
$skipped = 0;

foreach ($files_to_copy as $file) {
    $src = $ftp_base . '/' . $file;
    $dest = $correct_base . '/' . $file;

    echo "  $file: ";

    if (!file_exists($src)) {
        echo "SKIP (source not found)\n";
        $skipped++;
        continue;
    }

    // Create directory if needed
    $dest_dir = dirname($dest);
    if (!is_dir($dest_dir)) {
        mkdir($dest_dir, 0755, true);
        echo "(created dir) ";
    }

    if (copy($src, $dest)) {
        echo "OK (" . filesize($dest) . " bytes)\n";
        $copied++;
    } else {
        echo "FAILED\n";
        $failed++;
    }
}

echo "\nCopied: $copied, Failed: $failed, Skipped: $skipped\n\n";

// Create data/chunks directory
echo "Creating data directories...\n";
$data_dir = $correct_base . '/data';
$chunks_dir = $correct_base . '/data/chunks';

if (!is_dir($data_dir)) {
    mkdir($data_dir, 0755, true);
    echo "  Created: /data/\n";
} else {
    echo "  Exists: /data/\n";
}

if (!is_dir($chunks_dir)) {
    mkdir($chunks_dir, 0755, true);
    echo "  Created: /data/chunks/\n";
} else {
    echo "  Exists: /data/chunks/\n";
}

// Security index files
file_put_contents($data_dir . '/index.php', '<?php http_response_code(403); exit;');
file_put_contents($chunks_dir . '/index.php', '<?php http_response_code(403); exit;');
echo "  Added security index files\n\n";

// Setup database tables
echo "Setting up database tables...\n";
require_once $correct_base . '/config/database.php';

try {
    $pdo = db();

    // Create upload_chunks table
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS upload_chunks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            device_id INT NOT NULL,
            chunk_filename VARCHAR(255) NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            file_size BIGINT DEFAULT 0,
            compressed_size BIGINT DEFAULT 0,
            row_count INT DEFAULT 0,
            checksum VARCHAR(64),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_device_id (device_id),
            INDEX idx_period (period_start, period_end),
            UNIQUE KEY unique_chunk (device_id, period_start, period_end)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ");
    echo "  OK: upload_chunks table\n";

    // Create device_activity_log table
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS device_activity_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            device_id INT NOT NULL,
            action VARCHAR(50) NOT NULL,
            ip_address VARCHAR(45),
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_device_id (device_id),
            INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ");
    echo "  OK: device_activity_log table\n";

    // Verify pi_devices exists and check count
    $stmt = $pdo->query("SELECT COUNT(*) FROM pi_devices");
    $count = $stmt->fetchColumn();
    echo "  OK: Found $count registered devices\n";

} catch (PDOException $e) {
    echo "  ERROR: " . $e->getMessage() . "\n";
}

echo "\n==============================================\n";
echo "Installation Complete!\n";
echo "==============================================\n\n";

echo "Test the APIs:\n";
echo "  curl -H 'X-API-Key: YOUR_KEY' https://poolaissistant.modprojects.co.uk/api/list_chunks.php\n\n";

// Cleanup
echo "Cleaning up...\n";
@unlink($ftp_base . '/check_paths.php');
@unlink($ftp_base . '/setup_chunks.php');
echo "  Removed diagnostic files\n";

echo "\nIMPORTANT: Delete this installer file!\n";
echo "  Access: https://poolai.modprojects.co.uk/install_chunks_api.php?cleanup=1\n";

if (isset($_GET['cleanup'])) {
    unlink(__FILE__);
    echo "\nInstaller deleted.\n";
}
