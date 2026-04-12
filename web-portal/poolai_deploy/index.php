<?php
/**
 * PoolAI Portal - Smart Entry Point
 * Redirects to dashboard if logged in, otherwise shows login
 */

require_once __DIR__ . '/includes/PortalAuth.php';

$auth = new PortalAuth();

if ($auth->isLoggedIn()) {
    header('Location: dashboard.php');
} else {
    header('Location: login.php');
}
exit;
