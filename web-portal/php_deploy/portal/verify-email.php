<?php
// Retired 2026-05-03. Customer portal lives at poolai.modprojects.co.uk now.
// Verification tokens emitted before retirement were scoped to the poolai.*
// PortalAuth instance; preserving the query string lets the redirect resolve.
$qs = $_SERVER['QUERY_STRING'] ?? '';
$dest = 'https://poolai.modprojects.co.uk/verify-email.php' . ($qs !== '' ? '?' . $qs : '');
header('Location: ' . $dest, true, 301);
exit;
