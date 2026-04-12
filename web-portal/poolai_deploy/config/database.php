<?php
/**
 * Database Configuration for PoolAI Portal
 * Connects to the same database as poolaissistant.modprojects.co.uk
 */

function db(): PDO {
    static $pdo = null;

    if ($pdo === null) {
        $host = 'localhost';
        $dbname = 'u931726538_PoolAIssistant';
        $username = 'u931726538_mbs_modproject';
        $password = 'PoolAI2026!';

        try {
            $pdo = new PDO(
                "mysql:host=$host;dbname=$dbname;charset=utf8mb4",
                $username,
                $password,
                [
                    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                    PDO::ATTR_EMULATE_PREPARES => false
                ]
            );
        } catch (PDOException $e) {
            error_log("Database connection failed: " . $e->getMessage());
            http_response_code(500);
            die(json_encode(['error' => 'Database connection failed']));
        }
    }

    return $pdo;
}
