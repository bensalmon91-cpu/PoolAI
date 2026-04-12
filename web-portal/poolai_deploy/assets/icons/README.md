# PWA Icons for PoolAIssistant

This directory should contain the following icon files for the PWA to work correctly.

## Required Icons

Generate these from a 1024x1024 source image with the PoolAIssistant logo:

### Standard Icons (square)
- `icon-72.png` - 72x72
- `icon-96.png` - 96x96
- `icon-128.png` - 128x128
- `icon-144.png` - 144x144
- `icon-152.png` - 152x152
- `icon-192.png` - 192x192
- `icon-384.png` - 384x384
- `icon-512.png` - 512x512

### Maskable Icons (with safe zone padding)
- `icon-maskable-192.png` - 192x192 (icon centered in safe zone)
- `icon-maskable-512.png` - 512x512 (icon centered in safe zone)

### Favicons
- `favicon-16.png` - 16x16
- `favicon-32.png` - 32x32

### Apple Touch Icon
- `apple-touch-icon.png` - 180x180

### Safari Pinned Tab (SVG)
- `safari-pinned-tab.svg` - Monochrome SVG

### Screenshots (optional, for app store listing)
- `dashboard.png` - 390x844 (iPhone size)

## Quick Generation

You can use online tools like:
- https://realfavicongenerator.net/ - Generates all favicon variants
- https://maskable.app/ - Create maskable icons with safe zone
- https://pwa-asset-generator.dev/ - Generates all PWA icons from one source

## Icon Guidelines

1. **Standard icons**: Full bleed, no padding needed
2. **Maskable icons**: Keep the main content within the center 80% (safe zone)
3. **Apple touch icon**: Slightly rounded corners look better on iOS
4. **Favicon**: Simple, recognizable at small sizes

## Design Recommendations

- Primary color: #0066cc (blue)
- Background: White or transparent
- Style: Simple pool/water icon or "PA" monogram
