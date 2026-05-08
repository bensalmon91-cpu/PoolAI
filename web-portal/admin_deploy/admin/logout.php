<?php
/**
 * Admin Logout
 */

require_once __DIR__ . '/../includes/auth.php';

logoutAdmin();
header('Location: /admin/login.php');
exit;
