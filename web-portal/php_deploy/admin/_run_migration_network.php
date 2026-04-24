<?php
/**
 * One-off migration runner: adds device_health.network_json for v6.12+ Pi heartbeats.
 *
 * Admin-guarded. Idempotent (checks information_schema before adding).
 * Self-deletes after success so the endpoint can't be re-hit.
 *
 * Usage: log into /admin/, visit /admin/_run_migration_network.php once.
 */

declare(strict_types=1);

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

header('Content-Type: text/plain; charset=utf-8');

$pdo = db();

echo "Migration: device_health.network_json\n";
echo "======================================\n\n";

try {
    $stmt = $pdo->prepare("
        SELECT COUNT(*) AS n
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'device_health'
          AND column_name = 'network_json'
    ");
    $stmt->execute();
    $exists = (int)$stmt->fetch(PDO::FETCH_ASSOC)['n'] > 0;

    if ($exists) {
        echo "[OK] network_json column already exists. Nothing to do.\n";
    } else {
        $pdo->exec("ALTER TABLE device_health ADD COLUMN network_json JSON NULL AFTER issues_json");
        echo "[OK] Added network_json column to device_health.\n";
    }

    if (@unlink(__FILE__)) {
        echo "[OK] Migration runner self-deleted.\n";
    } else {
        echo "[WARN] Could not self-delete. Remove the file manually.\n";
    }
} catch (PDOException $e) {
    echo "[ERROR] " . $e->getMessage() . "\n";
    exit(1);
}
