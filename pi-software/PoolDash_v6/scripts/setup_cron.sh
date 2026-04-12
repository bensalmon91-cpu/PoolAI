#!/bin/bash
# Setup automated data management cron jobs for PoolAIssistant

SCRIPT_DIR="/opt/PoolAIssistant/app/scripts"
LOG_DIR="/opt/PoolAIssistant/logs"
DATA_DIR="/opt/PoolAIssistant/data"

# Create log directory
mkdir -p "$LOG_DIR"

# Generate cron entries
CRON_ENTRIES=$(cat <<'EOF'
# PoolAIssistant Data Management Jobs
# -----------------------------------

# Chunk Manager: Create and upload compressed data chunks every 6 hours
# Uploads to backend and deletes local chunks after successful upload
0 */6 * * * cd /opt/PoolAIssistant/app && /opt/PoolAIssistant/venv/bin/python ~/chunk_manager.py >> /opt/PoolAIssistant/logs/chunk_manager.log 2>&1

# Data Retention: Downsample old data daily at 3 AM
# - Data older than 30 days -> hourly averages
# - Data older than 365 days -> deleted
0 3 * * * cd /opt/PoolAIssistant/app && /opt/PoolAIssistant/venv/bin/python ~/data_retention.py --force >> /opt/PoolAIssistant/logs/data_retention.log 2>&1

# Database Optimization: Weekly vacuum and analyze on Sunday at 4 AM
0 4 * * 0 cd /opt/PoolAIssistant/app && /usr/bin/python3 scripts/db_optimize.py >> /opt/PoolAIssistant/logs/db_optimize.log 2>&1
EOF
)

# Get current crontab (or empty if none)
CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")

# Check if our jobs are already installed
if echo "$CURRENT_CRON" | grep -q "chunk_manager.py"; then
    echo "Cron jobs already installed. Updating..."
    # Remove old PoolAIssistant entries
    NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "PoolAIssistant\|chunk_manager\|data_retention\|db_optimize")
else
    echo "Installing new cron jobs..."
    NEW_CRON="$CURRENT_CRON"
fi

# Add new entries
echo "$NEW_CRON
$CRON_ENTRIES" | crontab -

echo "Cron jobs installed successfully!"
echo ""
echo "Scheduled jobs:"
echo "  - Chunk upload: Every 6 hours"
echo "  - Data retention: Daily at 3 AM"
echo "  - DB optimization: Weekly on Sunday at 4 AM"
echo ""
echo "Log files will be written to: $LOG_DIR"
echo ""
echo "Current crontab:"
crontab -l
