<?php
header('Content-Type: text/plain');
$src = '/home/u931726538/domains/poolai.modprojects.co.uk/public_html/api/delete_chunks.php';
$dest = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/api/delete_chunks.php';

if (copy($src, $dest)) {
    echo "OK: Copied delete_chunks.php (" . filesize($dest) . " bytes)\n";
    @unlink($src);
    @unlink(__FILE__);
    echo "Cleaned up installer files.\n";
} else {
    echo "FAILED to copy delete_chunks.php\n";
}
