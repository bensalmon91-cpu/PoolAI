<?php
require_once __DIR__ . '/../config/database.php';
$pdo = db();

$version = '6.7.2';
$filename = 'update-v6.7.2.tar.gz';
$file_size = 2359520;
$checksum = 'c084e502daddbb47c82055cd3660a4bae777331a419b0fe3b753eeedf8fe4090';
$description = 'v6.7.2 - Critical AP/WiFi connectivity fixes:
- Fixed dnsmasq conf-dir not being read (DHCP not working)
- Changed Flask to port 80 (captive portal now reachable)
- Added captive portal handlers for iOS/Android
- Fixed FIRST_BOOT marker location inconsistency
- Added file locking to prevent settings corruption
- Fixed SSID inconsistency (PoolAId -> PoolAI)
- Updated kiosk scripts for port 80';

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
