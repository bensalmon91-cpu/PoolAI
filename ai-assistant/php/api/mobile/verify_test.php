<?php
// Temporary script to verify test user - DELETE AFTER USE
header('Content-Type: text/plain');

require_once __DIR__ . '/../../config/database.php';

$pdo = db();

// Check current status
$stmt = $pdo->prepare("SELECT id, email, status, email_verified FROM portal_users WHERE email = ?");
$stmt->execute(['test@poolai.test']);
$user = $stmt->fetch(PDO::FETCH_ASSOC);
print_r($user);

// Update to active and verified
$stmt = $pdo->prepare("UPDATE portal_users SET email_verified = 1, status = 'active' WHERE email = ?");
$stmt->execute(['test@poolai.test']);

echo "\nRows updated: " . $stmt->rowCount() . "\n";
echo "Test user activated and verified!\n";
