<?php
// Retired 2026-05-08. Admin moved to admin.modprojects.co.uk.
// See web-portal/CLAUDE.md → "Domain split" for context.
$reqUri = $_SERVER['REQUEST_URI'] ?? '/admin/';
header('Location: https://admin.modprojects.co.uk' . $reqUri, true, 308);
exit;
