#!/bin/bash
#
# install_boot_check.sh - Install the boot check service
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/PoolAIssistant/app"

echo "Installing PoolAIssistant Boot Check..."

# Copy boot_check.sh to app directory
sudo cp "$SCRIPT_DIR/boot_check.sh" "$APP_DIR/scripts/"
sudo chmod +x "$APP_DIR/scripts/boot_check.sh"

# Install systemd service
sudo cp "$SCRIPT_DIR/systemd/poolaissistant_boot_check.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_boot_check.service

echo "Boot check service installed and enabled."
echo ""
echo "To test manually: sudo /opt/PoolAIssistant/app/scripts/boot_check.sh"
echo "To check status:  cat /opt/PoolAIssistant/data/boot_status.json"
echo "To view logs:     journalctl -u poolaissistant_boot_check"
