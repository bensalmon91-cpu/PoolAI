#!/bin/bash
# ========================================
# PoolAIssistant Pre-Configuration Script
# ========================================
# Pre-configure a cloned SD card with site-specific settings before shipping
# Usage: ./pre_configure.sh <mount_point> <site_config.json>

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <mount_point> <site_config.json>"
    echo
    echo "Example:"
    echo "  $0 /mnt/sd_card site_abc.json"
    echo
    echo "The mount_point should be the root of the SD card's ext4 partition."
    echo "The site_config.json should contain the site-specific controller configuration."
    exit 1
fi

MOUNT_POINT="$1"
CONFIG_FILE="$2"

# Validate mount point
if [ ! -d "$MOUNT_POINT" ]; then
    echo "ERROR: Mount point does not exist: $MOUNT_POINT"
    exit 1
fi

# Validate config file
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file does not exist: $CONFIG_FILE"
    exit 1
fi

# Check if mount point looks like a PoolAIssistant SD card
if [ ! -d "$MOUNT_POINT/opt/PoolAIssistant" ]; then
    echo "ERROR: Mount point does not appear to be a PoolAIssistant SD card"
    echo "Expected to find: $MOUNT_POINT/opt/PoolAIssistant"
    exit 1
fi

DATA_DIR="$MOUNT_POINT/opt/PoolAIssistant/data"

echo "========================================"
echo "PoolAIssistant Pre-Configuration"
echo "========================================"
echo
echo "Mount point: $MOUNT_POINT"
echo "Config file: $CONFIG_FILE"
echo

# Validate JSON
if ! python3 -m json.tool "$CONFIG_FILE" > /dev/null 2>&1; then
    echo "ERROR: Invalid JSON in config file"
    exit 1
fi

# Show config preview
echo "Configuration preview:"
echo "---"
cat "$CONFIG_FILE" | python3 -m json.tool
echo "---"
echo

read -p "Apply this configuration? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

# Copy site-specific settings to SD card
echo "Copying settings to SD card..."
sudo cp "$CONFIG_FILE" "$DATA_DIR/pooldash_settings.json"
sudo chown 1000:1000 "$DATA_DIR/pooldash_settings.json"  # Default Pi user UID/GID
echo "OK - Settings copied"

# Mark as pre-configured
echo "Marking as pre-configured..."
sudo touch "$DATA_DIR/PRE_CONFIGURED"
sudo chown 1000:1000 "$DATA_DIR/PRE_CONFIGURED"
echo "OK - Pre-configured marker created"

# Remove first-boot marker if present
if [ -f "$DATA_DIR/FIRST_BOOT" ]; then
    sudo rm -f "$DATA_DIR/FIRST_BOOT"
    echo "OK - First-boot marker removed"
fi

echo
echo "========================================"
echo "Pre-Configuration Complete!"
echo "========================================"
echo
echo "The SD card is now configured for:"
cat "$CONFIG_FILE" | python3 -c "import sys, json; cfg=json.load(sys.stdin); print(f\"  {len(cfg.get('controllers', []))} controller(s)\")"

echo
echo "Next steps:"
echo "1. Safely unmount the SD card:"
echo "   sync && sudo umount $MOUNT_POINT"
echo
echo "2. Insert SD card into Pi and boot"
echo
echo "3. The Pi will auto-configure on first boot using these settings"
echo
echo "4. Access web UI at: http://<pi-ip>:8080"
echo
