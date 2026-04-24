#!/bin/bash
#
# install_boot_check.sh - Install the boot check service
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/PoolAIssistant/app"

echo "Installing PoolAIssistant Boot Check..."

# Copy boot_check.sh into the app dir, unless it's already there.
# The installer is usually run from within $APP_DIR/scripts/, so src == dst
# and cp fails with "are the same file". Guard against it.
BOOT_CHECK_SRC="$SCRIPT_DIR/boot_check.sh"
BOOT_CHECK_DST="$APP_DIR/scripts/boot_check.sh"
if [ "$(readlink -f "$BOOT_CHECK_SRC")" != "$(readlink -f "$BOOT_CHECK_DST")" ]; then
    sudo cp "$BOOT_CHECK_SRC" "$BOOT_CHECK_DST"
fi
sudo chmod +x "$BOOT_CHECK_DST"

# Install systemd service
sudo cp "$SCRIPT_DIR/systemd/poolaissistant_boot_check.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_boot_check.service

echo "Boot check service installed and enabled."
echo ""
echo "To test manually: sudo /opt/PoolAIssistant/app/scripts/boot_check.sh"
echo "To check status:  cat /opt/PoolAIssistant/data/boot_status.json"
echo "To view logs:     journalctl -u poolaissistant_boot_check"
