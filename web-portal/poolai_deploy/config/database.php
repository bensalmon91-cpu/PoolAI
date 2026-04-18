<?php
/**
 * Database Configuration for PoolAI Portal
 *
 * Connects to the same shared MySQL database as the admin backend at
 * poolaissistant.modprojects.co.uk. Credentials are loaded from a local
 * .env file at poolai_deploy/.env so they are never committed to source.
 *
 * .env format:
 *   DB_HOST=localhost
 *   DB_NAME=u931726538_PoolAIssistant
 *   DB_USER=u931726538_mbs_modproject
 *   DB_PASS=<secret>
 */

if (!function_exists('portal_load_env')) {
    function portal_load_env(): void {
        static $loaded = false;
        if ($loaded) return;
        $loaded = true;

        $envFile = __DIR__ . '/../.env';
        if (!file_exists($envFile)) return;

        foreach (file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            $line = ltrim($line);
            if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) continue;
            [$name, $value] = explode('=', $line, 2);
            $name = trim($name);
            $value = trim($value, " \t\n\r\0\x0B\"'");
            if ($name !== '' && getenv($name) === false) {
                putenv("$name=$value");
                $_ENV[$name] = $value;
            }
        }
    }
}

function db(): PDO {
    static $pdo = null;

    if ($pdo === null) {
        portal_load_env();

        $host = getenv('DB_HOST') ?: 'localhost';
        $dbname = getenv('DB_NAME') ?: '';
        $username = getenv('DB_USER') ?: '';
        $password = getenv('DB_PASS') ?: '';

        if ($dbname === '' || $username === '') {
            http_response_code(500);
            error_log('poolai_deploy: DB credentials missing. Expected poolai_deploy/.env with DB_NAME/DB_USER/DB_PASS.');
            die(json_encode(['error' => 'Database configuration missing']));
        }

        try {
            $pdo = new PDO(
                "mysql:host=$host;dbname=$dbname;charset=utf8mb4",
                $username,
                $password,
                [
                    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                    PDO::ATTR_EMULATE_PREPARES => false,
                ]
            );
        } catch (PDOException $e) {
            error_log('poolai_deploy: DB connect failed: ' . $e->getMessage());
            http_response_code(500);
            die(json_encode(['error' => 'Database connection failed']));
        }
    }

    return $pdo;
}
