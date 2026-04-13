#!/bin/bash
# Configure the scheduled daily reboot timer based on settings
# Called when settings change or at boot

set -e

SETTINGS_FILE="${POOLDASH_SETTINGS_PATH:-/opt/PoolAIssistant/data/pooldash_settings.json}"
TIMER_NAME="poolaissistant_scheduled_reboot.timer"
SERVICE_DIR="/etc/systemd/system"
APP_SYSTEMD_DIR="/opt/PoolAIssistant/app/scripts/systemd"

# Read settings using Python (handles JSON properly)
read_setting() {
    python3 -c "
import json
try:
    with open('$SETTINGS_FILE') as f:
        data = json.load(f)
    print(data.get('$1', '$2'))
except:
    print('$2')
" 2>/dev/null
}

# Get settings
ENABLED=$(read_setting "scheduled_reboot_enabled" "true")
REBOOT_TIME=$(read_setting "scheduled_reboot_time" "04:00")

# Validate time format (default to 04:00 if invalid)
if ! echo "$REBOOT_TIME" | grep -qE '^([01]?[0-9]|2[0-3]):[0-5][0-9]$'; then
    REBOOT_TIME="04:00"
fi

# Normalize time to HH:MM
HOUR=$(echo "$REBOOT_TIME" | cut -d: -f1)
MINUTE=$(echo "$REBOOT_TIME" | cut -d: -f2)
REBOOT_TIME=$(printf "%02d:%02d" "$HOUR" "$MINUTE")

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring scheduled reboot: enabled=$ENABLED, time=$REBOOT_TIME"

# Ensure service file is installed
if [ -f "$APP_SYSTEMD_DIR/poolaissistant_scheduled_reboot.service" ]; then
    cp "$APP_SYSTEMD_DIR/poolaissistant_scheduled_reboot.service" "$SERVICE_DIR/"
fi

# Create/update timer with configured time
cat > "$SERVICE_DIR/$TIMER_NAME" << EOF
[Unit]
Description=PoolAIssistant Daily Scheduled Reboot

[Timer]
OnCalendar=*-*-* ${REBOOT_TIME}:00
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable or disable based on setting
if [ "$ENABLED" = "true" ] || [ "$ENABLED" = "True" ] || [ "$ENABLED" = "1" ]; then
    systemctl enable "$TIMER_NAME" 2>/dev/null || true
    systemctl start "$TIMER_NAME" 2>/dev/null || true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduled reboot enabled at $REBOOT_TIME daily"

    # Show next scheduled reboot
    systemctl list-timers "$TIMER_NAME" --no-pager 2>/dev/null | head -3 || true
else
    systemctl stop "$TIMER_NAME" 2>/dev/null || true
    systemctl disable "$TIMER_NAME" 2>/dev/null || true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduled reboot disabled"
fi

# Disable old weekly reboot timer if it exists
if systemctl is-enabled poolaissistant_weekly_reboot.timer 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Disabling old weekly reboot timer"
    systemctl stop poolaissistant_weekly_reboot.timer 2>/dev/null || true
    systemctl disable poolaissistant_weekly_reboot.timer 2>/dev/null || true
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduled reboot configuration complete"
