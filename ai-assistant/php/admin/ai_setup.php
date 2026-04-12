<?php
/**
 * AI Assistant Setup Script
 * Creates AI tables and seeds initial questions
 *
 * IMPORTANT: Delete this file after setup!
 */

require_once __DIR__ . '/../config/database.php';

$message = '';
$error = '';
$pdo = db();

// Check current state
$tables_exist = [];
$required_tables = ['ai_questions', 'ai_question_queue', 'ai_responses', 'ai_pool_profiles', 'ai_suggestions', 'ai_pool_norms', 'ai_conversation_log'];

foreach ($required_tables as $table) {
    try {
        $stmt = $pdo->query("SELECT 1 FROM $table LIMIT 1");
        $tables_exist[$table] = true;
    } catch (PDOException $e) {
        $tables_exist[$table] = false;
    }
}

$all_tables_exist = !in_array(false, $tables_exist, true);

// Check if questions are seeded
$questions_count = 0;
if ($tables_exist['ai_questions']) {
    try {
        $questions_count = $pdo->query("SELECT COUNT(*) FROM ai_questions")->fetchColumn();
    } catch (PDOException $e) {}
}

// Process form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';

    if ($action === 'run_migration') {
        try {
            // Create ai_questions table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_questions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    text TEXT NOT NULL,
                    type ENUM('onboarding', 'periodic', 'event', 'followup', 'contextual') NOT NULL,
                    category VARCHAR(50),
                    input_type ENUM('buttons', 'dropdown', 'text', 'number', 'date') DEFAULT 'buttons',
                    options_json TEXT,
                    trigger_condition TEXT,
                    priority TINYINT DEFAULT 3,
                    frequency VARCHAR(20),
                    follow_up_to INT NULL,
                    admin_notes TEXT,
                    is_active TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (follow_up_to) REFERENCES ai_questions(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            // Create ai_question_queue table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_question_queue (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT UNSIGNED NOT NULL,
                    question_id INT NOT NULL,
                    pool VARCHAR(100) DEFAULT '',
                    triggered_by VARCHAR(200),
                    status ENUM('pending', 'delivered', 'answered', 'expired', 'skipped') DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivered_at TIMESTAMP NULL,
                    answered_at TIMESTAMP NULL,
                    expires_at TIMESTAMP NULL,
                    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
                    FOREIGN KEY (question_id) REFERENCES ai_questions(id) ON DELETE CASCADE,
                    INDEX idx_device_status (device_id, status),
                    INDEX idx_created (created_at),
                    INDEX idx_expires (expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            // Create ai_responses table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_responses (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT UNSIGNED NOT NULL,
                    question_id INT NOT NULL,
                    queue_id BIGINT NOT NULL,
                    pool VARCHAR(100) NOT NULL DEFAULT '',
                    answer TEXT NOT NULL,
                    answer_json TEXT,
                    answered_at TIMESTAMP NOT NULL,
                    flagged TINYINT(1) DEFAULT 0,
                    admin_notes TEXT,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
                    FOREIGN KEY (question_id) REFERENCES ai_questions(id) ON DELETE CASCADE,
                    FOREIGN KEY (queue_id) REFERENCES ai_question_queue(id) ON DELETE CASCADE,
                    INDEX idx_device_pool (device_id, pool),
                    INDEX idx_answered (answered_at),
                    INDEX idx_flagged (flagged)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            // Create ai_pool_profiles table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_pool_profiles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT UNSIGNED NOT NULL,
                    pool VARCHAR(100) NOT NULL DEFAULT '',
                    profile_json TEXT NOT NULL,
                    patterns_json TEXT,
                    maturity_score TINYINT UNSIGNED DEFAULT 0,
                    questions_answered INT UNSIGNED DEFAULT 0,
                    last_question_at TIMESTAMP NULL,
                    last_analysis_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_device_pool (device_id, pool),
                    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            // Create ai_suggestions table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_suggestions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT UNSIGNED NOT NULL,
                    pool VARCHAR(100) NOT NULL DEFAULT '',
                    suggestion_type VARCHAR(50),
                    title VARCHAR(200) NOT NULL,
                    body TEXT NOT NULL,
                    priority TINYINT DEFAULT 3,
                    confidence DECIMAL(3,2),
                    source_data_json TEXT,
                    status ENUM('pending', 'delivered', 'read', 'acted_upon', 'dismissed', 'retracted') DEFAULT 'pending',
                    admin_notes TEXT,
                    retracted_at TIMESTAMP NULL,
                    retracted_reason TEXT,
                    delivered_at TIMESTAMP NULL,
                    read_at TIMESTAMP NULL,
                    user_action TEXT,
                    user_feedback TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
                    INDEX idx_device_status (device_id, status),
                    INDEX idx_created (created_at),
                    INDEX idx_type (suggestion_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            // Create ai_pool_norms table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_pool_norms (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    pool_type VARCHAR(50) NOT NULL,
                    metric VARCHAR(50) NOT NULL,
                    value DECIMAL(10,4) NOT NULL,
                    sample_count INT UNSIGNED,
                    min_value DECIMAL(10,4),
                    max_value DECIMAL(10,4),
                    std_dev DECIMAL(10,4),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_type_metric (pool_type, metric)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            // Create ai_conversation_log table
            $pdo->exec("
                CREATE TABLE IF NOT EXISTS ai_conversation_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT UNSIGNED NULL,
                    pool VARCHAR(100),
                    action_type VARCHAR(50) NOT NULL,
                    prompt_summary TEXT,
                    response_summary TEXT,
                    tokens_used INT UNSIGNED,
                    model_version VARCHAR(50),
                    duration_ms INT UNSIGNED,
                    success TINYINT(1) DEFAULT 1,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_device (device_id),
                    INDEX idx_action (action_type),
                    INDEX idx_created (created_at),
                    INDEX idx_success (success)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ");

            $message = 'All AI tables created successfully!';

            // Refresh table state
            foreach ($required_tables as $table) {
                $tables_exist[$table] = true;
            }
            $all_tables_exist = true;

        } catch (PDOException $e) {
            $error = 'Migration error: ' . $e->getMessage();
        }
    }

    if ($action === 'seed_questions') {
        try {
            // Check if questions already exist
            $count = $pdo->query("SELECT COUNT(*) FROM ai_questions")->fetchColumn();
            if ($count > 0) {
                $message = 'Questions already seeded (' . $count . ' questions exist).';
            } else {
                // Seed questions
                $questions = [
                    ['What type of pool is this?', 'onboarding', 'environment', 'buttons', '["Indoor Public", "Outdoor Public", "Indoor Private", "Outdoor Private", "Spa/Hot Tub", "Hydrotherapy"]', 1, 'once', 'Essential for establishing baseline norms'],
                    ['Approximately what is the pool volume?', 'onboarding', 'environment', 'dropdown', '["Under 50,000 litres", "50,000 - 100,000 litres", "100,000 - 250,000 litres", "250,000 - 500,000 litres", "Over 500,000 litres", "Unknown"]', 1, 'once', 'Needed for dosing calculations'],
                    ['What is the typical daily bather load?', 'onboarding', 'environment', 'buttons', '["Light (under 50)", "Moderate (50-200)", "Heavy (200-500)", "Very Heavy (500+)"]', 2, 'once', 'Affects chlorine demand'],
                    ['What type of filtration system does this pool use?', 'onboarding', 'equipment', 'buttons', '["Sand Filter", "DE Filter", "Cartridge Filter", "Glass Media", "Other/Unknown"]', 2, 'once', 'Affects backwash recommendations'],
                    ['How is chemical dosing managed?', 'onboarding', 'equipment', 'buttons', '["Fully Automatic", "Semi-Automatic", "Manual Dosing"]', 2, 'once', 'Determines dosing recommendation type'],
                    ['What is the primary water source?', 'onboarding', 'environment', 'buttons', '["Mains Water", "Well/Borehole", "Mixed/Other"]', 3, 'once', 'Affects hardness considerations'],
                    ['What brand of pool controller is installed?', 'onboarding', 'equipment', 'dropdown', '["ezetrol", "Prominent", "Signet", "Siemens", "Grundfos", "Other", "Multiple Brands"]', 2, 'once', 'Helps interpret readings'],
                    ['When were the pH and chlorine probes last calibrated?', 'onboarding', 'maintenance', 'buttons', '["Within the last month", "1-3 months ago", "3-6 months ago", "Over 6 months ago", "Not sure"]', 2, 'once', 'Critical for data accuracy'],
                    ['Are there any known ongoing issues with this pool?', 'onboarding', 'maintenance', 'text', NULL, 3, 'once', 'Free text for specific challenges'],
                    ['When was the filter last serviced or backwashed?', 'periodic', 'maintenance', 'buttons', '["Today", "Within the last week", "1-2 weeks ago", "Over 2 weeks ago", "Not sure"]', 3, 'monthly', 'Regular filter maintenance check'],
                    ['Have the probes been calibrated recently?', 'periodic', 'maintenance', 'buttons', '["Yes, within the last month", "No, need calibration soon", "Not sure"]', 3, 'monthly', 'Monthly calibration reminder'],
                    ['pH has been reading high for an extended period. Have you checked the following?', 'event', 'water_quality', 'buttons', '["Checked probe - needs calibration", "Checked probe - looks fine", "Adjusted dosing", "Investigating cause", "Need help"]', 1, 'on_event', 'Triggered on pH anomaly'],
                    ['Chlorine levels have been lower than expected. What might be causing this?', 'event', 'water_quality', 'buttons', '["High bather load recently", "Chemical supply running low", "Dosing system issue", "Hot weather/sun exposure", "Not sure"]', 1, 'on_event', 'Triggered on chlorine anomaly'],
                    ['You recently performed a backwash. How long did the filter pressure take to stabilize?', 'contextual', 'equipment', 'buttons', '["Immediately", "Within an hour", "Several hours", "Still not stable", "Did not monitor"]', 4, 'on_event', 'Learn filter behavior'],
                    ['You mentioned algae concerns previously. Has the situation improved?', 'followup', 'water_quality', 'buttons', '["Yes, fully resolved", "Improving but not clear", "No change", "Getting worse"]', 2, 'on_event', 'Follow-up to algae response'],
                ];

                $stmt = $pdo->prepare("
                    INSERT INTO ai_questions (text, type, category, input_type, options_json, priority, frequency, admin_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ");

                foreach ($questions as $q) {
                    $stmt->execute($q);
                }

                $questions_count = count($questions);
                $message = "Seeded $questions_count questions successfully!";
            }
        } catch (PDOException $e) {
            $error = 'Seeding error: ' . $e->getMessage();
        }
    }
}

// Re-check questions count
if ($tables_exist['ai_questions'] ?? false) {
    try {
        $questions_count = $pdo->query("SELECT COUNT(*) FROM ai_questions")->fetchColumn();
    } catch (PDOException $e) {}
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Setup - PoolAIssistant</title>
    <style>
        :root { --bg: #0f172a; --surface: #1e293b; --accent: #8b5cf6; --text: #f1f5f9; --success: #22c55e; --warning: #f59e0b; --danger: #ef4444; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 40px 20px; }
        .container { max-width: 700px; margin: 0 auto; }
        h1 { margin-bottom: 10px; }
        h1 span { color: var(--accent); }
        .subtitle { color: #94a3b8; margin-bottom: 30px; }
        .card { background: var(--surface); padding: 24px; border-radius: 12px; margin-bottom: 24px; }
        .card h2 { font-size: 1.125rem; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        .status { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .status.done { background: rgba(34,197,94,0.2); color: var(--success); }
        .status.pending { background: rgba(245,158,11,0.2); color: var(--warning); }
        .table-list { margin: 16px 0; }
        .table-item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #334155; font-size: 0.875rem; }
        .table-item:last-child { border-bottom: none; }
        .table-name { font-family: monospace; color: #94a3b8; }
        .btn { padding: 10px 20px; border: none; border-radius: 6px; background: var(--accent); color: white; cursor: pointer; font-weight: 600; }
        .btn:hover { background: #7c3aed; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-secondary { background: #334155; }
        .btn-secondary:hover { background: #475569; }
        .message { padding: 12px; border-radius: 8px; margin-bottom: 20px; }
        .message.success { background: rgba(34,197,94,0.1); color: var(--success); }
        .message.error { background: rgba(239,68,68,0.1); color: var(--danger); }
        .warning { background: rgba(245,158,11,0.1); color: var(--warning); padding: 16px; border-radius: 8px; margin-top: 24px; }
        .next-steps { background: var(--surface); padding: 24px; border-radius: 12px; margin-top: 24px; }
        .next-steps h3 { margin-bottom: 16px; }
        .next-steps ol { margin-left: 20px; line-height: 2; }
        .next-steps a { color: var(--accent); }
        .flex { display: flex; gap: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1><span>AI</span> Assistant Setup</h1>
        <p class="subtitle">Configure the AI Assistant database tables and seed initial questions.</p>

        <?php if ($message): ?>
            <div class="message success"><?= htmlspecialchars($message) ?></div>
        <?php endif; ?>

        <?php if ($error): ?>
            <div class="message error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <div class="card">
            <h2>
                1. Database Tables
                <span class="status <?= $all_tables_exist ? 'done' : 'pending' ?>">
                    <?= $all_tables_exist ? 'All Created' : 'Pending' ?>
                </span>
            </h2>
            <p style="color: #94a3b8; margin-bottom: 16px;">Creates 7 tables for the AI system.</p>

            <div class="table-list">
                <?php foreach ($required_tables as $table): ?>
                <div class="table-item">
                    <span class="table-name"><?= $table ?></span>
                    <span class="status <?= $tables_exist[$table] ? 'done' : 'pending' ?>">
                        <?= $tables_exist[$table] ? 'Exists' : 'Missing' ?>
                    </span>
                </div>
                <?php endforeach; ?>
            </div>

            <form method="POST">
                <input type="hidden" name="action" value="run_migration">
                <button type="submit" class="btn" <?= $all_tables_exist ? 'disabled' : '' ?>>
                    <?= $all_tables_exist ? 'Tables Already Created' : 'Create AI Tables' ?>
                </button>
            </form>
        </div>

        <div class="card">
            <h2>
                2. Seed Questions
                <span class="status <?= $questions_count > 0 ? 'done' : 'pending' ?>">
                    <?= $questions_count > 0 ? "$questions_count Questions" : 'Not Seeded' ?>
                </span>
            </h2>
            <p style="color: #94a3b8; margin-bottom: 16px;">Adds 15 default onboarding and periodic questions.</p>

            <form method="POST">
                <input type="hidden" name="action" value="seed_questions">
                <button type="submit" class="btn" <?= !$all_tables_exist ? 'disabled' : '' ?>>
                    <?= $questions_count > 0 ? 'Re-seed Questions' : 'Seed Questions' ?>
                </button>
            </form>
        </div>

        <?php if ($all_tables_exist && $questions_count > 0): ?>
        <div class="next-steps">
            <h3>Setup Complete! Next Steps:</h3>
            <ol>
                <li>Visit the <a href="ai_dashboard.php">AI Dashboard</a> to verify everything works</li>
                <li>Add <code>CLAUDE_API_KEY</code> to your .env file when ready</li>
                <li>Modify <code>heartbeat.php</code> to include AI sync (see INTEGRATION.md)</li>
                <li><strong>Delete this setup file</strong> for security</li>
            </ol>
        </div>
        <?php endif; ?>

        <div class="warning">
            <strong>Security Notice:</strong> Delete this ai_setup.php file after completing setup to prevent unauthorized access.
        </div>
    </div>
</body>
</html>
