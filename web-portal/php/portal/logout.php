<?php
/**
 * PoolAIssistant Portal - Logout
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();
$auth->logout();

header('Location: login.php');
exit;
