<?php
/**
 * One-shot cleanup: remove retired admin-only files from
 * poolaissistant.modprojects.co.uk that were moved to admin.* in the
 * 2026-05-08 admin migration. deploy.py's php_installer mode never
 * deletes; this script catches up.
 *
 * Drop into FTP root of poolai.* (chroot the FTP user lands in),
 * then HTTPS-GET this URL. It runs unlink() on a hardcoded list of
 * server-absolute paths, then self-deletes.
 *
 * Safety:
 *   - All paths are hardcoded constants (no user input).
 *   - Each path is validated to live under the expected base.
 *   - Listing-only mode (?dry=1) for previewing without changes.
 *   - Self-deletes on success.
 */

error_reporting(E_ALL);
ini_set('display_errors', 1);
header('Content-Type: text/plain; charset=utf-8');
set_time_limit(120);

const BASE = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant';

$dry = !empty($_GET['dry']);

// Files to remove (relative to BASE).
$files = [
    'api/admin/_verify.php',
    'api/admin/client_actions.php',
    'api/admin_device_command.php',
    'api/admin_health.php',
    'api/admin_request_upload.php',
    'api/admin_update_setting.php',
    'api/clear_device_issues.php',
    'api/delete_device.php',
    'api/queue_test_question.php',
    'api/ai/generate.php',
    'api/ai/norms.php',
    'api/ai/profiles.php',
    'api/ai/questions.php',
    'api/ai/queue.php',
    'api/ai/responses.php',
    'api/ai/suggestions.php',
    'includes/AdminClients.php',
    'includes/AdminDevices.php',
    'includes/RemoteSettings.php',
    'includes/claude_api.php',
    'staff/api/checkin.php',
    'staff/api/dashboard.php',
    'staff/assets/app.js',
    'staff/assets/styles.css',
    'staff/icon.php',
    'staff/index.php',
    'staff/login.php',
    'staff/logout.php',
    'staff/manifest.json',
    'staff/sw.js',
];

// Directories to remove AFTER their files (deepest first).
$dirs = [
    'api/admin',
    'staff/api',
    'staff/assets',
    'staff',
];

echo "Admin-cruft cleanup for " . BASE . "\n";
echo "Mode: " . ($dry ? 'DRY-RUN (no changes)' : 'EXECUTE') . "\n";
echo str_repeat('-', 60) . "\n";

$base_real = realpath(BASE);
if ($base_real === false) {
    die("[ERROR] BASE not resolvable: " . BASE . "\n");
}

$removed_files = 0;
$missing_files = 0;
$failed_files  = [];

foreach ($files as $rel) {
    $full = $base_real . '/' . $rel;
    // Defense in depth: must live under BASE.
    if (strpos(realpath(dirname($full)), $base_real) !== 0) {
        echo sprintf("[REJECT] %-50s outside BASE\n", $rel);
        continue;
    }
    if (!file_exists($full)) {
        echo sprintf("[MISS  ] %-50s (already gone)\n", $rel);
        $missing_files++;
        continue;
    }
    if ($dry) {
        echo sprintf("[WOULD ] %-50s %d bytes\n", $rel, filesize($full));
        continue;
    }
    if (@unlink($full)) {
        echo sprintf("[DEL   ] %-50s\n", $rel);
        $removed_files++;
    } else {
        $err = error_get_last();
        echo sprintf("[FAIL  ] %-50s %s\n", $rel, $err['message'] ?? '?');
        $failed_files[] = $rel;
    }
}

echo "\n";

$removed_dirs = 0;
$missing_dirs = 0;
$nonempty_dirs = [];

foreach ($dirs as $rel) {
    $full = $base_real . '/' . $rel;
    if (!is_dir($full)) {
        echo sprintf("[MISS  ] %-50s (not a dir / gone)\n", $rel);
        $missing_dirs++;
        continue;
    }
    if ($dry) {
        $contents = array_diff(scandir($full), ['.', '..']);
        echo sprintf("[WOULD ] %-50s (contains %d entries)\n", $rel, count($contents));
        continue;
    }
    if (@rmdir($full)) {
        echo sprintf("[RMDIR ] %-50s\n", $rel);
        $removed_dirs++;
    } else {
        $contents = is_dir($full) ? array_diff(scandir($full), ['.', '..']) : [];
        echo sprintf("[KEEP  ] %-50s (still has %d entries: %s)\n",
            $rel, count($contents), implode(', ', array_slice($contents, 0, 5)));
        $nonempty_dirs[] = $rel;
    }
}

echo "\n" . str_repeat('-', 60) . "\n";
echo "Summary:\n";
echo "  Files removed: $removed_files\n";
echo "  Files already missing: $missing_files\n";
echo "  Files failed: " . count($failed_files) . (count($failed_files) ? ' (' . implode(', ', $failed_files) . ')' : '') . "\n";
echo "  Dirs removed: $removed_dirs\n";
echo "  Dirs already missing: $missing_dirs\n";
echo "  Dirs not empty: " . count($nonempty_dirs) . "\n";

if ($dry) {
    echo "\nDRY-RUN complete. Re-fetch this URL without ?dry=1 to execute.\n";
} elseif (empty($failed_files)) {
    echo "\nCleanup OK. Self-deleting.\n";
    @unlink(__FILE__);
    echo "[OK] Bundle self-deleted.\n";
} else {
    echo "\nSome failures - leaving script in place for retry/inspection.\n";
}
