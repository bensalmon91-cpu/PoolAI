<?php
/**
 * Claude API Integration
 *
 * Wrapper class for Anthropic Claude API calls.
 * All AI interactions go through this class for consistency and logging.
 */

require_once __DIR__ . '/../config/config.php';
require_once __DIR__ . '/../config/database.php';

class ClaudeAPI {
    private string $api_key;
    private string $model;
    private string $api_url = 'https://api.anthropic.com/v1/messages';
    private int $max_tokens;
    private PDO $pdo;

    public function __construct(?string $api_key = null, string $model = 'claude-sonnet-4-20250514', int $max_tokens = 1024) {
        $this->api_key = $api_key ?? env('CLAUDE_API_KEY', '');
        $this->model = $model;
        $this->max_tokens = $max_tokens;
        $this->pdo = db();

        if (empty($this->api_key)) {
            throw new Exception('Claude API key not configured. Set CLAUDE_API_KEY in .env');
        }
    }

    /**
     * Send a message to Claude and get a response
     */
    public function message(string $system_prompt, string $user_message, array $options = []): array {
        $start_time = microtime(true);

        $payload = [
            'model' => $options['model'] ?? $this->model,
            'max_tokens' => $options['max_tokens'] ?? $this->max_tokens,
            'system' => $system_prompt,
            'messages' => [
                ['role' => 'user', 'content' => $user_message]
            ]
        ];

        if (isset($options['temperature'])) {
            $payload['temperature'] = $options['temperature'];
        }

        $ch = curl_init($this->api_url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'x-api-key: ' . $this->api_key,
                'anthropic-version: 2023-06-01'
            ],
            CURLOPT_POSTFIELDS => json_encode($payload),
            CURLOPT_TIMEOUT => 60
        ]);

        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curl_error = curl_error($ch);
        curl_close($ch);

        $duration_ms = (int)((microtime(true) - $start_time) * 1000);

        if ($curl_error) {
            return [
                'success' => false,
                'error' => 'Network error: ' . $curl_error,
                'duration_ms' => $duration_ms
            ];
        }

        $data = json_decode($response, true);

        if ($http_code !== 200) {
            $error_msg = $data['error']['message'] ?? 'Unknown API error';
            return [
                'success' => false,
                'error' => "API error ($http_code): $error_msg",
                'duration_ms' => $duration_ms
            ];
        }

        $content = '';
        if (isset($data['content']) && is_array($data['content'])) {
            foreach ($data['content'] as $block) {
                if ($block['type'] === 'text') {
                    $content .= $block['text'];
                }
            }
        }

        $input_tokens = $data['usage']['input_tokens'] ?? 0;
        $output_tokens = $data['usage']['output_tokens'] ?? 0;

        return [
            'success' => true,
            'content' => $content,
            'tokens_used' => $input_tokens + $output_tokens,
            'input_tokens' => $input_tokens,
            'output_tokens' => $output_tokens,
            'model' => $data['model'] ?? $this->model,
            'duration_ms' => $duration_ms
        ];
    }

    /**
     * Analyze a user response to a question and update pool profile
     */
    public function analyzeResponse(int $device_id, string $pool, array $question, string $answer, array $profile = []): array {
        $system_prompt = <<<PROMPT
You are an expert pool water quality consultant analyzing responses from pool operators.
Your job is to:
1. Extract key information from the response
2. Identify any concerns or follow-up questions needed
3. Update the pool profile with new information
4. Flag unusual or concerning responses

Respond in JSON format with these fields:
{
  "profile_updates": { /* key-value pairs to merge into profile */ },
  "concerns": [ /* array of concern strings, or empty */ ],
  "follow_up_question_ids": [ /* IDs of follow-up questions to queue, or empty */ ],
  "flag_for_admin": false, /* true if admin should review */
  "flag_reason": null, /* reason for flagging, if any */
  "insights": [ /* any insights about this pool */ ]
}
PROMPT;

        $context = [
            'question_text' => $question['text'],
            'question_type' => $question['type'],
            'question_category' => $question['category'],
            'answer' => $answer,
            'current_profile' => $profile
        ];

        $user_message = "Analyze this pool operator response:\n\n" . json_encode($context, JSON_PRETTY_PRINT);

        $result = $this->message($system_prompt, $user_message, ['temperature' => 0.3]);

        if ($result['success']) {
            $parsed = $this->extractJson($result['content']);
            $result['analysis'] = $parsed;
        }

        $this->logConversation(
            $device_id,
            $pool,
            'analyze_response',
            "Q: {$question['text']} | A: " . substr($answer, 0, 100),
            $result['success'] ? substr($result['content'], 0, 500) : $result['error'],
            $result['tokens_used'] ?? 0,
            $result['model'] ?? $this->model,
            $result['duration_ms'] ?? 0,
            $result['success']
        );

        return $result;
    }

    /**
     * Generate suggestions for a pool based on data and profile
     */
    public function generateSuggestions(
        int $device_id,
        string $pool,
        array $readings,
        array $alarms,
        array $profile,
        array $previous_suggestions = []
    ): array {
        $system_prompt = <<<PROMPT
You are an expert pool water quality consultant generating actionable suggestions for pool operators.

Based on the data provided, generate 1-3 practical, specific suggestions.
Each suggestion should be:
- Actionable (the operator can do something about it)
- Specific (not generic advice)
- Prioritized (most important first)
- Confident (only suggest things you're reasonably sure about)

Respond in JSON format:
{
  "suggestions": [
    {
      "type": "water_quality|dosing|maintenance|equipment|operational",
      "title": "Short title (under 60 chars)",
      "body": "Detailed explanation and steps to take",
      "priority": 1-5, /* 1 = highest priority */
      "confidence": 0.0-1.0
    }
  ],
  "pool_grade": "A|B|C|D|F", /* overall water quality grade */
  "grade_reasoning": "Brief explanation of grade"
}

If no suggestions are needed, return empty suggestions array.
PROMPT;

        $context = [
            'pool_profile' => $profile,
            'recent_readings' => $readings,
            'recent_alarms' => $alarms,
            'previous_suggestions' => array_map(fn($s) => $s['title'], $previous_suggestions)
        ];

        $user_message = "Generate suggestions for this pool:\n\n" . json_encode($context, JSON_PRETTY_PRINT);

        $result = $this->message($system_prompt, $user_message, ['temperature' => 0.5]);

        if ($result['success']) {
            $parsed = $this->extractJson($result['content']);
            $result['suggestions'] = $parsed['suggestions'] ?? [];
            $result['pool_grade'] = $parsed['pool_grade'] ?? null;
        }

        $this->logConversation(
            $device_id,
            $pool,
            'generate_suggestion',
            'Profile + ' . count($readings) . ' readings + ' . count($alarms) . ' alarms',
            $result['success'] ? (count($result['suggestions'] ?? []) . ' suggestions') : $result['error'],
            $result['tokens_used'] ?? 0,
            $result['model'] ?? $this->model,
            $result['duration_ms'] ?? 0,
            $result['success']
        );

        return $result;
    }

    /**
     * Detect anomalies by comparing pool to norms
     */
    public function detectAnomalies(int $device_id, string $pool, array $pool_stats, array $norms): array {
        $system_prompt = <<<PROMPT
You are a pool analytics expert detecting anomalies by comparing individual pool data against cross-pool norms.

Identify any significant deviations that warrant investigation.
Consider:
- Statistical outliers (>2 standard deviations)
- Concerning trends
- Equipment performance issues
- Unusual patterns

Respond in JSON:
{
  "anomalies": [
    {
      "metric": "metric name",
      "severity": "low|medium|high",
      "description": "What's unusual",
      "recommendation": "What to investigate"
    }
  ],
  "overall_health": "good|fair|poor",
  "summary": "Brief overall assessment"
}
PROMPT;

        $context = [
            'pool_statistics' => $pool_stats,
            'reference_norms' => $norms
        ];

        $user_message = "Detect anomalies for this pool:\n\n" . json_encode($context, JSON_PRETTY_PRINT);

        $result = $this->message($system_prompt, $user_message, ['temperature' => 0.2]);

        if ($result['success']) {
            $parsed = $this->extractJson($result['content']);
            $result['anomalies'] = $parsed['anomalies'] ?? [];
            $result['overall_health'] = $parsed['overall_health'] ?? null;
        }

        $this->logConversation(
            $device_id,
            $pool,
            'detect_anomaly',
            'Stats comparison against ' . count($norms) . ' norms',
            $result['success'] ? (count($result['anomalies'] ?? []) . ' anomalies') : $result['error'],
            $result['tokens_used'] ?? 0,
            $result['model'] ?? $this->model,
            $result['duration_ms'] ?? 0,
            $result['success']
        );

        return $result;
    }

    /**
     * Extract JSON from a response that might have surrounding text
     */
    private function extractJson(string $content): array {
        $data = json_decode($content, true);
        if (json_last_error() === JSON_ERROR_NONE && is_array($data)) {
            return $data;
        }

        if (preg_match('/\{[\s\S]*\}/', $content, $matches)) {
            $data = json_decode($matches[0], true);
            if (json_last_error() === JSON_ERROR_NONE && is_array($data)) {
                return $data;
            }
        }

        return [];
    }

    /**
     * Log a conversation to the database
     */
    private function logConversation(
        ?int $device_id,
        ?string $pool,
        string $action_type,
        string $prompt_summary,
        string $response_summary,
        int $tokens_used,
        string $model_version,
        int $duration_ms,
        bool $success
    ): void {
        try {
            $stmt = $this->pdo->prepare("
                INSERT INTO ai_conversation_log
                (device_id, pool, action_type, prompt_summary, response_summary,
                 tokens_used, model_version, duration_ms, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ");
            $stmt->execute([
                $device_id,
                $pool,
                $action_type,
                substr($prompt_summary, 0, 500),
                substr($response_summary, 0, 500),
                $tokens_used,
                $model_version,
                $duration_ms,
                $success ? 1 : 0
            ]);
        } catch (PDOException $e) {
            error_log("Failed to log Claude conversation: " . $e->getMessage());
        }
    }

    /**
     * Get API usage statistics
     */
    public function getUsageStats(int $days = 30): array {
        $stmt = $this->pdo->prepare("
            SELECT
                DATE(created_at) as date,
                action_type,
                COUNT(*) as calls,
                SUM(tokens_used) as total_tokens,
                AVG(duration_ms) as avg_duration_ms,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
            FROM ai_conversation_log
            WHERE created_at > DATE_SUB(NOW(), INTERVAL ? DAY)
            GROUP BY DATE(created_at), action_type
            ORDER BY date DESC, action_type
        ");
        $stmt->execute([$days]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }
}
