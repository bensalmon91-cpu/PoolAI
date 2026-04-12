#!/bin/bash
# Install weekly reboot timer for PoolAIssistant
# Run with: sudo bash install_weekly_reboot.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing weekly reboot timer..."

sudo cp "$SCRIPT_DIR/systemd/poolaissistant_weekly_reboot.timer" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/systemd/poolaissistant_weekly_reboot.service" /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_weekly_reboot.timer
sudo systemctl start poolaissistant_weekly_reboot.timer

echo ""
echo "Weekly reboot timer installed and enabled."
echo "The Pi will reboot every Sunday at 4:00 AM."
echo ""
systemctl status poolaissistant_weekly_reboot.timer --no-pager
