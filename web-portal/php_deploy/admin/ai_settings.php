<?php
/**
 * AI Assistant Settings
 * Configure Claude API and view system status
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();
$message = '';
$error = '';

// Ensure ai_settings table exists
try {
    $pdo->query("SELECT 1 FROM ai_settings LIMIT 1");
} catch (PDOException $e) {
    // Create the table
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS ai_settings (
            setting_key VARCHAR(50) PRIMARY KEY,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ");

    // Insert defaults
    $defaults = [
        ['claude_api_key', ''],
        ['claude_model', 'claude-sonnet-4-20250514'],
        ['max_tokens', '1024'],
        ['auto_analyze', '1'],
        ['backup_enabled', '1'],
        ['backup_path', '/data/ai_backups/']
    ];

    $stmt = $pdo->prepare("INSERT IGNORE INTO ai_settings (setting_key, setting_value) VALUES (?, ?)");
    foreach ($defaults as $d) {
        $stmt->execute($d);
    }
}

// Helper to get setting
function getSetting($pdo, $key, $default = '') {
    $stmt = $pdo->prepare("SELECT setting_value FROM ai_settings WHERE setting_key = ?");
    $stmt->execute([$key]);
    $result = $stmt->fetchColumn();
    return $result !== false ? $result : $default;
}

// Helper to set setting
function setSetting($pdo, $key, $value) {
    $stmt = $pdo->prepare("INSERT INTO ai_settings (setting_key, setting_value) VALUES (?, ?) ON DUPLICATE KEY UPDATE setting_value = ?");
    $stmt->execute([$key, $value, $value]);
}

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';

    if ($action === 'save_settings') {
        try {
            // Save API key (only if provided - don't overwrite with empty)
            $api_key = trim($_POST['api_key'] ?? '');
            if (!empty($api_key)) {
                setSetting($pdo, 'claude_api_key', $api_key);
            }

            setSetting($pdo, 'claude_model', $_POST['model'] ?? 'claude-sonnet-4-20250514');
            setSetting($pdo, 'max_tokens', $_POST['max_tokens'] ?? '1024');
            setSetting($pdo, 'auto_analyze', isset($_POST['auto_analyze']) ? '1' : '0');
            setSetting($pdo, 'backup_enabled', isset($_POST['backup_enabled']) ? '1' : '0');

            $message = 'Settings saved successfully!';
        } catch (Exception $e) {
            $error = 'Error saving settings: ' . $e->getMessage();
        }
    }

    if ($action === 'test_connection') {
        $api_key = getSetting($pdo, 'claude_api_key');
        if (empty($api_key)) {
            $error = 'API key not configured. Please save your API key first.';
        } else {
            // Test the API connection
            $ch = curl_init('https://api.anthropic.com/v1/messages');
            curl_setopt_array($ch, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_POST => true,
                CURLOPT_HTTPHEADER => [
                    'Content-Type: application/json',
                    'x-api-key: ' . $api_key,
                    'anthropic-version: 2023-06-01'
                ],
                CURLOPT_POSTFIELDS => json_encode([
                    'model' => getSetting($pdo, 'claude_model', 'claude-sonnet-4-20250514'),
                    'max_tokens' => 10,
                    'messages' => [['role' => 'user', 'content' => 'Say "connected" and nothing else.']]
                ])
            ]);

            $response = curl_exec($ch);
            $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            curl_close($ch);

            if ($http_code === 200) {
                $data = json_decode($response, true);
                $model_used = $data['model'] ?? 'unknown';
                $message = 'Connection successful! Claude API is working. Model: ' . $model_used;
            } else {
                $data = json_decode($response, true);
                $error_msg = $data['error']['message'] ?? 'Unknown error';
                $error_type = $data['error']['type'] ?? '';

                // Provide helpful context for common errors
                if ($http_code === 400 && strpos($error_msg, 'credit balance') !== false) {
                    $error = 'Billing issue: ' . $error_msg . ' - Check that your API key belongs to the organization where you added credits at console.anthropic.com';
                } else if ($http_code === 401) {
                    $error = 'Invalid API key. Please check the key is correct and active.';
                } else if ($http_code === 403) {
                    $error = 'Access denied. Your API key may not have permission for this model.';
                } else {
                    $error = 'Connection failed (HTTP ' . $http_code . '): ' . $error_msg;
                }
            }
        }
    }

    if ($action === 'backup_now') {
        // Create manual backup of all AI data
        try {
            $backup_data = [
                'exported_at' => date('Y-m-d H:i:s'),
                'pool_profiles' => $pdo->query("SELECT * FROM ai_pool_profiles")->fetchAll(PDO::FETCH_ASSOC),
                'responses' => $pdo->query("SELECT * FROM ai_responses ORDER BY answered_at DESC LIMIT 1000")->fetchAll(PDO::FETCH_ASSOC),
                'suggestions' => $pdo->query("SELECT * FROM ai_suggestions ORDER BY created_at DESC LIMIT 1000")->fetchAll(PDO::FETCH_ASSOC),
                'conversation_log' => $pdo->query("SELECT * FROM ai_conversation_log ORDER BY created_at DESC LIMIT 500")->fetchAll(PDO::FETCH_ASSOC),
                'pool_norms' => $pdo->query("SELECT * FROM ai_pool_norms")->fetchAll(PDO::FETCH_ASSOC)
            ];

            header('Content-Type: application/json');
            header('Content-Disposition: attachment; filename="ai_backup_' . date('Y-m-d_His') . '.json"');
            echo json_encode($backup_data, JSON_PRETTY_PRINT);
            exit;
        } catch (Exception $e) {
            $error = 'Backup failed: ' . $e->getMessage();
        }
    }
}

// Load current settings
$settings = [
    'api_key' => getSetting($pdo, 'claude_api_key'),
    'model' => getSetting($pdo, 'claude_model', 'claude-sonnet-4-20250514'),
    'max_tokens' => getSetting($pdo, 'max_tokens', '1024'),
    'auto_analyze' => getSetting($pdo, 'auto_analyze', '1'),
    'backup_enabled' => getSetting($pdo, 'backup_enabled', '1')
];

// Get usage stats
$stats = [];
try {
    $stats['total_api_calls'] = $pdo->query("SELECT COUNT(*) FROM ai_conversation_log")->fetchColumn();
    $stats['total_tokens'] = $pdo->query("SELECT COALESCE(SUM(tokens_used), 0) FROM ai_conversation_log")->fetchColumn();
    $stats['calls_today'] = $pdo->query("SELECT COUNT(*) FROM ai_conversation_log WHERE DATE(created_at) = CURDATE()")->fetchColumn();
    $stats['tokens_today'] = $pdo->query("SELECT COALESCE(SUM(tokens_used), 0) FROM ai_conversation_log WHERE DATE(created_at) = CURDATE()")->fetchColumn();
    $stats['success_rate'] = $pdo->query("SELECT ROUND(AVG(success) * 100, 1) FROM ai_conversation_log")->fetchColumn() ?? 100;
} catch (Exception $e) {
    // Tables might not have data yet
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Settings - PoolAIssistant</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-2: #334155;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --purple: #8b5cf6;
            --border: #475569;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }
        header h1 { font-size: 1.5rem; font-weight: 600; }
        header h1 span { color: var(--purple); }

        .nav-links { display: flex; gap: 8px; }
        .nav-links a {
            background: var(--surface-2);
            color: var(--text);
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.875rem;
        }
        .nav-links a:hover { background: var(--border); }
        .nav-links a.active { background: var(--purple); }

        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

        .card {
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
        }
        .card-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--surface-2);
            font-weight: 600;
        }
        .card-body { padding: 20px; }

        .form-group { margin-bottom: 20px; }
        .form-group label {
            display: block;
            margin-bottom: 6px;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .form-group input[type="text"],
        .form-group input[type="password"],
        .form-group input[type="number"],
        .form-group select {
            width: 100%;
            padding: 10px 12px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--surface-2);
            color: var(--text);
            font-size: 0.875rem;
        }
        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: var(--accent);
        }
        .form-group .help-text {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .checkbox-group input[type="checkbox"] {
            width: 18px;
            height: 18px;
            accent-color: var(--purple);
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            border: none;
            text-decoration: none;
            transition: all 0.15s;
        }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent-hover); }
        .btn-secondary { background: var(--surface-2); color: var(--text); }
        .btn-secondary:hover { background: var(--border); }
        .btn-success { background: var(--success); color: white; }
        .btn-purple { background: var(--purple); color: white; }
        .btn-purple:hover { background: #7c3aed; }

        .message {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.875rem;
        }
        .message.success { background: rgba(34, 197, 94, 0.1); color: var(--success); }
        .message.error { background: rgba(239, 68, 68, 0.1); color: var(--danger); }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 16px;
        }
        .stat-item {
            text-align: center;
            padding: 16px;
            background: var(--surface-2);
            border-radius: 8px;
        }
        .stat-item .value {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--purple);
        }
        .stat-item .label {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .api-key-input {
            position: relative;
        }
        .api-key-input input {
            padding-right: 80px;
        }
        .api-key-input .toggle-btn {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            background: var(--surface);
            border: none;
            color: var(--text-muted);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            cursor: pointer;
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .status-indicator.configured { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .status-indicator.not-configured { background: rgba(245, 158, 11, 0.2); color: var(--warning); }

        .btn-group { display: flex; gap: 12px; flex-wrap: wrap; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><span>AI</span> Settings</h1>
            <nav class="nav-links">
                <a href="ai_dashboard.php">Dashboard</a>
                <a href="ai_questions.php">Questions</a>
                <a href="ai_responses.php">Responses</a>
                <a href="ai_suggestions.php">Suggestions</a>
                <a href="ai_learnings.php">Learnings</a>
                <a href="ai_settings.php" class="active">Settings</a>
                <a href="index.php">Devices</a>
            </nav>
        </header>

        <?php if ($message): ?>
            <div class="message success"><?= htmlspecialchars($message) ?></div>
        <?php endif; ?>

        <?php if ($error): ?>
            <div class="message error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <div class="grid">
            <div class="card">
                <div class="card-header">
                    Claude API Configuration
                    <span class="status-indicator <?= !empty($settings['api_key']) ? 'configured' : 'not-configured' ?>" style="float: right;">
                        <?= !empty($settings['api_key']) ? 'Configured' : 'Not Configured' ?>
                    </span>
                </div>
                <div class="card-body">
                    <form method="POST">
                        <input type="hidden" name="action" value="save_settings">

                        <div class="form-group">
                            <label>Claude API Key</label>
                            <div class="api-key-input">
                                <input type="password" name="api_key" id="apiKey"
                                       placeholder="<?= !empty($settings['api_key']) ? 'sk-ant-••••••••••••' : 'Enter your Anthropic API key' ?>"
                                       autocomplete="off">
                                <button type="button" class="toggle-btn" onclick="toggleApiKey()">Show</button>
                            </div>
                            <div class="help-text">Get your API key from <a href="https://console.anthropic.com/" target="_blank" style="color: var(--accent);">console.anthropic.com</a></div>
                        </div>

                        <div class="form-group">
                            <label>Model</label>
                            <select name="model">
                                <option value="claude-sonnet-4-20250514" <?= $settings['model'] === 'claude-sonnet-4-20250514' ? 'selected' : '' ?>>Claude Sonnet 4 (Recommended)</option>
                                <option value="claude-opus-4-20250514" <?= $settings['model'] === 'claude-opus-4-20250514' ? 'selected' : '' ?>>Claude Opus 4 (Most Capable)</option>
                                <option value="claude-3-5-haiku-20241022" <?= $settings['model'] === 'claude-3-5-haiku-20241022' ? 'selected' : '' ?>>Claude 3.5 Haiku (Fast & Economical)</option>
                            </select>
                        </div>

                        <div class="form-group">
                            <label>Max Tokens per Response</label>
                            <input type="number" name="max_tokens" value="<?= htmlspecialchars($settings['max_tokens']) ?>" min="100" max="4096">
                        </div>

                        <div class="form-group">
                            <div class="checkbox-group">
                                <input type="checkbox" name="auto_analyze" id="autoAnalyze" <?= $settings['auto_analyze'] === '1' ? 'checked' : '' ?>>
                                <label for="autoAnalyze" style="margin: 0;">Auto-analyze responses and generate suggestions</label>
                            </div>
                        </div>

                        <div class="form-group">
                            <div class="checkbox-group">
                                <input type="checkbox" name="backup_enabled" id="backupEnabled" <?= $settings['backup_enabled'] === '1' ? 'checked' : '' ?>>
                                <label for="backupEnabled" style="margin: 0;">Enable automatic daily backups</label>
                            </div>
                        </div>

                        <div class="btn-group">
                            <button type="submit" class="btn btn-primary">Save Settings</button>
                        </div>
                    </form>
                </div>
            </div>

            <div class="card">
                <div class="card-header">API Usage Statistics</div>
                <div class="card-body">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="value"><?= number_format($stats['total_api_calls'] ?? 0) ?></div>
                            <div class="label">Total API Calls</div>
                        </div>
                        <div class="stat-item">
                            <div class="value"><?= number_format($stats['total_tokens'] ?? 0) ?></div>
                            <div class="label">Total Tokens</div>
                        </div>
                        <div class="stat-item">
                            <div class="value"><?= number_format($stats['calls_today'] ?? 0) ?></div>
                            <div class="label">Calls Today</div>
                        </div>
                        <div class="stat-item">
                            <div class="value"><?= ($stats['success_rate'] ?? 100) ?>%</div>
                            <div class="label">Success Rate</div>
                        </div>
                    </div>

                    <div style="margin-top: 24px;">
                        <form method="POST" style="display: inline;">
                            <input type="hidden" name="action" value="test_connection">
                            <button type="submit" class="btn btn-secondary">Test Connection</button>
                        </form>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">Data Backup</div>
                <div class="card-body">
                    <p style="color: var(--text-muted); margin-bottom: 16px; font-size: 0.875rem;">
                        Export all AI learnings, pool profiles, responses, and suggestions as a JSON file for local backup.
                    </p>

                    <form method="POST">
                        <input type="hidden" name="action" value="backup_now">
                        <button type="submit" class="btn btn-purple">Download Backup</button>
                    </form>
                </div>
            </div>

            <div class="card">
                <div class="card-header">System Information</div>
                <div class="card-body">
                    <table style="width: 100%; font-size: 0.875rem;">
                        <tr>
                            <td style="padding: 8px 0; color: var(--text-muted);">PHP Version</td>
                            <td style="padding: 8px 0; text-align: right;"><?= PHP_VERSION ?></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: var(--text-muted);">cURL Enabled</td>
                            <td style="padding: 8px 0; text-align: right;"><?= function_exists('curl_init') ? 'Yes' : 'No' ?></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: var(--text-muted);">JSON Enabled</td>
                            <td style="padding: 8px 0; text-align: right;"><?= function_exists('json_encode') ? 'Yes' : 'No' ?></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: var(--text-muted);">Database</td>
                            <td style="padding: 8px 0; text-align: right;">Connected</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
    function toggleApiKey() {
        const input = document.getElementById('apiKey');
        const btn = event.target;
        if (input.type === 'password') {
            input.type = 'text';
            btn.textContent = 'Hide';
        } else {
            input.type = 'password';
            btn.textContent = 'Show';
        }
    }
    </script>
</body>
</html>
