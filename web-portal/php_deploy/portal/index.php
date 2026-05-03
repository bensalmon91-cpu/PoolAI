<?php
// Retired 2026-05-03. Customer portal lives at poolai.modprojects.co.uk now.
// See web-portal/CLAUDE.md → "Known architectural quirks" for context.
$qs = $_SERVER['QUERY_STRING'] ?? '';
$dest = 'https://poolai.modprojects.co.uk/' . ($qs !== '' ? '?' . $qs : '');
header('Location: ' . $dest, true, 301);
exit;
