<?php
/**
 * PoolAIssistant Portal API - Device Readings
 *
 * GET /api/portal/readings.php?device_id=X&range=24h&metric=pH
 *
 * Returns historical readings for charts.
 */

require_once __DIR__ . '/../../config/database.php';
require_once __DIR__ . '/../../includes/PortalAuth.php';
require_once __DIR__ . '/../../includes/PortalDevices.php';

header('Content-Type: application/json');

// Require authentication
$auth = new PortalAuth();
if (!$auth->isLoggedIn()) {
    http_response_code(401);
    echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
    exit;
}

$user = $auth->getUser();
$devicesManager = new PortalDevices($user['id']);

// Get parameters
$deviceId = intval($_GET['device_id'] ?? 0);
$range = $_GET['range'] ?? '24h';
$metric = $_GET['metric'] ?? null;
$pool = $_GET['pool'] ?? null;

if (!$deviceId) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'device_id required']);
    exit;
}

// Check access
if (!$devicesManager->hasAccess($deviceId)) {
    http_response_code(403);
    echo json_encode(['ok' => false, 'error' => 'Access denied']);
    exit;
}

// Parse range
$hours = 24;
switch ($range) {
    case '1h':
        $hours = 1;
        break;
    case '6h':
        $hours = 6;
        break;
    case '12h':
        $hours = 12;
        break;
    case '24h':
        $hours = 24;
        break;
    case '7d':
        $hours = 168;
        break;
    case '30d':
        $hours = 720;
        break;
    default:
        $hours = 24;
}

// Get readings
$readings = $devicesManager->getReadingsHistory($deviceId, $metric, $pool, $hours);

// Format for charts
$formatted = [];
foreach ($readings as $reading) {
    $key = $reading['pool'] . '|' . $reading['metric'];
    if (!isset($formatted[$key])) {
        $formatted[$key] = [
            'pool' => $reading['pool'],
            'metric' => $reading['metric'],
            'unit' => $reading['unit'],
            'data' => [],
        ];
    }
    $formatted[$key]['data'][] = [
        'ts' => $reading['ts'],
        'value' => floatval($reading['value']),
    ];
}

echo json_encode([
    'ok' => true,
    'device_id' => $deviceId,
    'range' => $range,
    'hours' => $hours,
    'series' => array_values($formatted),
]);
