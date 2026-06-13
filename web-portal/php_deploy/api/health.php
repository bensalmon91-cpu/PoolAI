<?php
/**
 * Health Check API
 * Simple endpoint to verify server is reachable
 *
 * GET /api/health.php
 * Returns: {"ok": true, "server": "poolaissistant", "timestamp": "..."}
 */

header('Content-Type: application/json');

echo json_encode([
    'ok' => true,
    'server' => 'poolaissistant',
    'timestamp' => date('c'),
    'version' => '1.0'
]);
