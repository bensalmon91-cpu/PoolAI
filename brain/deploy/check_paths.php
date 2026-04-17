<?php
header('Content-Type: text/plain');

echo "Checking file paths...\n\n";

$paths_to_check = [
    '/home/u931726538/public_html/poolaissistant/api/',
    '/home/u931726538/domains/poolai.modprojects.co.uk/public_html/api/',
    '/home/u931726538/public_html/api/',
    __DIR__ . '/api/',
    dirname(__DIR__) . '/api/',
];

foreach ($paths_to_check as $path) {
    echo "Path: $path\n";
    if (is_dir($path)) {
        echo "  EXISTS - Contents:\n";
        $files = scandir($path);
        foreach ($files as $f) {
            if ($f != '.' && $f != '..') {
                echo "    - $f\n";
            }
        }
    } else {
        echo "  NOT FOUND\n";
    }
    echo "\n";
}

echo "Current script location: " . __FILE__ . "\n";
echo "Document root: " . ($_SERVER['DOCUMENT_ROOT'] ?? 'not set') . "\n";
