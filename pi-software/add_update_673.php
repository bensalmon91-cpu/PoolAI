<?php
require_once __DIR__ . '/../config/database.php';
$pdo = db();

$version = '6.7.3';
$filename = 'update-v6.7.3.tar.gz';
$file_size = 2361536;
$checksum = '89786f740bb3c999c32223e07e2fe118dcc04a079f71131bc6640571038084e4';
$description = 'v6.7.3 - Robust port/firewall configuration:
- Added ensure_ports.sh script (works with UFW, iptables, nftables)
- New poolaissistant_ports.service runs at boot
- UI service now ensures ports are open before starting
- Fallback firewall configuration for all firewall types
- Fixed EnvironmentFile handling (optional with dash prefix)';

$stmt = $pdo->prepare("INSERT INTO software_updates (version, filename, file_size, checksum, description, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, NOW())");
$result = $stmt->execute([$version, $filename, $file_size, $checksum, $description]);

if ($result) {
    echo "SUCCESS: Added update v{$version} to database\n";
    echo "ID: " . $pdo->lastInsertId() . "\n";
} else {
    echo "ERROR: Failed to add update\n";
    print_r($stmt->errorInfo());
}
?>
