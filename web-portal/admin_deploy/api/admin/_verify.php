<?php
/**
 * Deploy drift-detection endpoint.
 *
 * POST /api/admin/_verify.php
 * Body: {"paths": ["admin/login.php", "includes/auth.php", ...]}
 *
 * Returns: {"ok": true, "sha256": {"<path>": "<hex>|null", ...}, "base": "..."}
 *
 * Requires an admin session (reuses requireAdmin). Path traversal is rejected
 * before any filesystem access. Used by web-portal/deploy.py's `verify`
 * subcommand to detect when live files drift from the repo (the exact
 * condition that hid today's silently-broken admin login for weeks).
 */

require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/api_helpers.php';

setCorsHeaders();
requireAdmin();
requireMethod('POST');

$input = getJsonInput();
$paths = $input['paths'] ?? [];
if (!is_array($paths)) {
    errorResponse('paths must be an array of relative file paths');
}
if (count($paths) > 1000) {
    errorResponse('too many paths (max 1000)');
}

// Resolve base = admin backend document root, normalized. __DIR__ here is
// /.../poolaissistant/api/admin so two levels up gets us to poolaissistant/.
$base = realpath(__DIR__ . '/../..');
if ($base === false) {
    errorResponse('server: cannot resolve base path', 500);
}
$baseWithSep = rtrim($base, '/\\') . DIRECTORY_SEPARATOR;

$out = [];
foreach ($paths as $raw) {
    if (!is_string($raw)) {
        $out[(string)$raw] = null;
        continue;
    }
    // Reject absolute paths and parent-dir escapes before touching disk.
    $rel = ltrim(str_replace('\\', '/', $raw), '/');
    if ($rel === '' || strpos($rel, '..') !== false || strpos($rel, "\0") !== false) {
        $out[$raw] = null;
        continue;
    }
    $full = $base . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $rel);
    $resolved = realpath($full);
    if ($resolved === false || strncmp($resolved, $baseWithSep, strlen($baseWithSep)) !== 0) {
        // Missing or outside base - report null.
        $out[$raw] = null;
        continue;
    }
    if (!is_file($resolved) || !is_readable($resolved)) {
        $out[$raw] = null;
        continue;
    }
    $out[$raw] = hash_file('sha256', $resolved);
}

successResponse([
    'sha256' => $out,
    'base' => $base,
    'count' => count($paths),
]);
