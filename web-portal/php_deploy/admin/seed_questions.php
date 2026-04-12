<?php
/**
 * Seed AI Questions
 * Adds initial onboarding questions if they don't exist
 */

require_once __DIR__ . '/../config/database.php';
require_once __DIR__ . '/../includes/auth.php';

requireAdmin();

$pdo = db();
$message = '';
$error = '';

// Check if questions exist
$count = $pdo->query("SELECT COUNT(*) FROM ai_questions")->fetchColumn();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['seed'])) {
    try {
        // Insert seed questions
        $pdo->exec("
            INSERT INTO ai_questions (text, type, category, input_type, options_json, priority, frequency, admin_notes) VALUES
            ('What type of pool is this?', 'onboarding', 'environment', 'buttons',
             '[\"Indoor Public\", \"Outdoor Public\", \"Indoor Private\", \"Outdoor Private\", \"Spa/Hot Tub\", \"Hydrotherapy\"]',
             1, 'once', 'Essential for establishing baseline norms'),

            ('Approximately what is the pool volume?', 'onboarding', 'environment', 'dropdown',
             '[\"Under 50,000 litres\", \"50,000 - 100,000 litres\", \"100,000 - 250,000 litres\", \"250,000 - 500,000 litres\", \"Over 500,000 litres\", \"Unknown\"]',
             1, 'once', 'Needed for dosing calculations'),

            ('What is the typical daily bather load?', 'onboarding', 'environment', 'buttons',
             '[\"Light (under 50)\", \"Moderate (50-200)\", \"Heavy (200-500)\", \"Very Heavy (500+)\"]',
             2, 'once', 'Affects chlorine demand'),

            ('What type of filtration system does this pool use?', 'onboarding', 'equipment', 'buttons',
             '[\"Sand Filter\", \"DE Filter\", \"Cartridge Filter\", \"Glass Media\", \"Other/Unknown\"]',
             2, 'once', 'Affects backwash recommendations'),

            ('How is chemical dosing managed?', 'onboarding', 'equipment', 'buttons',
             '[\"Fully Automatic\", \"Semi-Automatic\", \"Manual Dosing\"]',
             2, 'once', 'Determines dosing recommendations'),

            ('What brand of pool controller is installed?', 'onboarding', 'equipment', 'dropdown',
             '[\"ezetrol\", \"Prominent\", \"Signet\", \"Siemens\", \"Grundfos\", \"Other\", \"Multiple Brands\"]',
             2, 'once', 'Helps provide brand-specific advice'),

            ('When were the pH and chlorine probes last calibrated?', 'onboarding', 'maintenance', 'buttons',
             '[\"Within the last month\", \"1-3 months ago\", \"3-6 months ago\", \"Over 6 months ago\", \"Not sure\"]',
             2, 'once', 'Critical for data accuracy'),

            ('Are there any known ongoing issues with this pool?', 'onboarding', 'maintenance', 'text',
             NULL,
             3, 'once', 'Free text for specific challenges')
        ");

        $message = "Successfully added " . $pdo->query("SELECT COUNT(*) FROM ai_questions")->fetchColumn() . " questions!";
        $count = $pdo->query("SELECT COUNT(*) FROM ai_questions")->fetchColumn();
    } catch (PDOException $e) {
        $error = "Error: " . $e->getMessage();
    }
}

// Get current questions
$questions = $pdo->query("SELECT id, text, type, category, input_type FROM ai_questions WHERE is_active = 1 ORDER BY priority, id")->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html>
<head>
    <title>Seed Questions - PoolAIssistant</title>
    <style>
        body { font-family: system-ui; background: #0f172a; color: #f1f5f9; padding: 20px; }
        .card { background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px; }
        .btn { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: 500; }
        .btn-primary { background: #3b82f6; color: white; }
        .message { padding: 12px; border-radius: 8px; margin-bottom: 16px; }
        .message.success { background: rgba(34,197,94,0.1); color: #22c55e; }
        .message.error { background: rgba(239,68,68,0.1); color: #ef4444; }
        table { width: 100%; border-collapse: collapse; margin-top: 16px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; background: #334155; }
        a { color: #3b82f6; }
    </style>
</head>
<body>
    <h1>AI Questions Setup</h1>

    <?php if ($message): ?>
        <div class="message success"><?= htmlspecialchars($message) ?></div>
    <?php endif; ?>

    <?php if ($error): ?>
        <div class="message error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>

    <div class="card">
        <h2>Current Status: <?= $count ?> questions</h2>

        <?php if ($count == 0): ?>
            <p>No questions found. Click below to add the initial onboarding questions.</p>
            <form method="POST">
                <button type="submit" name="seed" value="1" class="btn btn-primary">Add Seed Questions</button>
            </form>
        <?php else: ?>
            <p>Questions are ready! You can now use the "Test AI" button on the dashboard.</p>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Question</th>
                        <th>Type</th>
                        <th>Category</th>
                        <th>Input</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($questions as $q): ?>
                    <tr>
                        <td><?= $q['id'] ?></td>
                        <td><?= htmlspecialchars(substr($q['text'], 0, 50)) ?><?= strlen($q['text']) > 50 ? '...' : '' ?></td>
                        <td><span class="badge"><?= $q['type'] ?></span></td>
                        <td><?= $q['category'] ?></td>
                        <td><?= $q['input_type'] ?></td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </div>

    <p><a href="index.php">&larr; Back to Dashboard</a> | <a href="ai_dashboard.php">AI Dashboard</a></p>
</body>
</html>
