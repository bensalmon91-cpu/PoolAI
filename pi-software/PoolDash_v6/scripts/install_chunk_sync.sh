#!/bin/bash
# Install the chunk sync service and timer on the Pi

set -e

echo "Installing Chunk Sync Service..."

# Copy service files
sudo cp /opt/PoolAIssistant/app/scripts/chunk_sync.service /etc/systemd/system/
sudo cp /opt/PoolAIssistant/app/scripts/chunk_sync.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the timer
sudo systemctl enable chunk_sync.timer
sudo systemctl start chunk_sync.timer

echo "Chunk sync timer installed and started."
echo "Chunks will be created and uploaded daily at 2:00 AM."
echo ""
echo "To run manually: sudo systemctl start chunk_sync.service"
echo "To check status: systemctl status chunk_sync.timer"
echo "To view logs: journalctl -u chunk_sync.service"
