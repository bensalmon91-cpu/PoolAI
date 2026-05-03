<?php
// Retired 2026-05-03. Customer portal lives at poolai.modprojects.co.uk now.
$qs = $_SERVER['QUERY_STRING'] ?? '';
$dest = 'https://poolai.modprojects.co.uk/login.php' . ($qs !== '' ? '?' . $qs : '');
header('Location: ' . $dest, true, 301);
exit;
