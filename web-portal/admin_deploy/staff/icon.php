<?php
/**
 * Dynamic PWA icon generator.
 *
 * PHP-rendered PNG so we don't need to ship binary assets. Produces a rounded
 * gradient tile with a "P" glyph. Accepts:
 *   ?size=192|512    pixel size (default 192, clamped 48..1024)
 *   ?maskable=1      fills the full canvas (no rounded corners) for maskable icons
 */

$size = max(48, min(1024, (int)($_GET['size'] ?? 192)));
$maskable = !empty($_GET['maskable']);

header('Content-Type: image/png');
header('Cache-Control: public, max-age=86400');

if (!function_exists('imagecreatetruecolor')) {
    // GD missing: fall back to a 1x1 transparent PNG so the manifest still
    // resolves without crashing the request.
    echo base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==');
    exit;
}

$im = imagecreatetruecolor($size, $size);
imagesavealpha($im, true);

// Transparent background
$transparent = imagecolorallocatealpha($im, 0, 0, 0, 127);
imagefilledrectangle($im, 0, 0, $size, $size, $transparent);

// Gradient tile: blue (#3b82f6) -> purple (#8b5cf6)
for ($y = 0; $y < $size; $y++) {
    $t = $y / max(1, $size - 1);
    $r = (int)round(0x3b + ($t * (0x8b - 0x3b)));
    $g = (int)round(0x82 + ($t * (0x5c - 0x82)));
    $b = (int)round(0xf6 + ($t * (0xf6 - 0xf6)));
    $col = imagecolorallocate($im, $r, $g, $b);
    imageline($im, 0, $y, $size - 1, $y, $col);
}

// If not maskable, clip to rounded square by masking corners transparent.
if (!$maskable) {
    $radius = (int)round($size * 0.22);
    for ($y = 0; $y < $size; $y++) {
        for ($x = 0; $x < $size; $x++) {
            $inside = true;
            // Top-left
            if ($x < $radius && $y < $radius) {
                $dx = $radius - $x; $dy = $radius - $y;
                if ($dx * $dx + $dy * $dy > $radius * $radius) $inside = false;
            }
            // Top-right
            if ($inside && $x >= $size - $radius && $y < $radius) {
                $dx = $x - ($size - $radius - 1); $dy = $radius - $y;
                if ($dx * $dx + $dy * $dy > $radius * $radius) $inside = false;
            }
            // Bottom-left
            if ($inside && $x < $radius && $y >= $size - $radius) {
                $dx = $radius - $x; $dy = $y - ($size - $radius - 1);
                if ($dx * $dx + $dy * $dy > $radius * $radius) $inside = false;
            }
            // Bottom-right
            if ($inside && $x >= $size - $radius && $y >= $size - $radius) {
                $dx = $x - ($size - $radius - 1); $dy = $y - ($size - $radius - 1);
                if ($dx * $dx + $dy * $dy > $radius * $radius) $inside = false;
            }
            if (!$inside) imagesetpixel($im, $x, $y, $transparent);
        }
    }
}

// Big white "P" in the middle using the largest built-in font, scaled via a
// small bitmap blown up with imagecopyresampled.
$letter = 'P';
$font = 5; // largest GD built-in
$glyphW = imagefontwidth($font);
$glyphH = imagefontheight($font);

$small = imagecreatetruecolor($glyphW, $glyphH);
imagesavealpha($small, true);
$trS = imagecolorallocatealpha($small, 0, 0, 0, 127);
imagefilledrectangle($small, 0, 0, $glyphW, $glyphH, $trS);
$white = imagecolorallocate($small, 255, 255, 255);
imagestring($small, $font, 0, 0, $letter, $white);

$target = (int)round($size * 0.62);
$dstX = (int)round(($size - $target) / 2);
$dstY = (int)round(($size - $target) / 2);
imagecopyresampled($im, $small, $dstX, $dstY, 0, 0, $target, $target, $glyphW, $glyphH);
imagedestroy($small);

imagepng($im);
imagedestroy($im);
