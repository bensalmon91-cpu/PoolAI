<?php
$version = '6.9.39';
$checksum = 'c16a1c6ba0db24cbc4faca59f77cd316e103367510cdeced51c8cfd4b4c337d9';
$description = 'Fix 23 critical/high/medium issues: WiFi escaping, AP config, screen rotation, input validation';
$filename = "update-v{$version}.tar.gz";

$src = __DIR__ . '/' . $filename;
$dest_dir = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/data/updates/';
$dest = $dest_dir . $filename;

if (!file_exists($src)) { die("Source not found: $src"); }
if (!is_dir($dest_dir)) { mkdir($dest_dir, 0755, true); }

if (copy($src, $dest)) {
    echo "Copied to $dest (" . filesize($dest) . " bytes)\n";

    require_once '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/config/database.php';
    $pdo = db();
    $stmt = $pdo->prepare("INSERT INTO software_updates (version, filename, file_size, checksum, description, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, NOW()) ON DUPLICATE KEY UPDATE file_size=VALUES(file_size), checksum=VALUES(checksum), is_active=1");
    $stmt->execute([$version, $filename, filesize($dest), $checksum, $description]);
    echo "Database updated\n";

    unlink($src);
    unlink(__FILE__);
    echo "Done!\n";
} else {
    echo "Copy failed\n";
}
