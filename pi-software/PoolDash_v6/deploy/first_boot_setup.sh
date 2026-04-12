#!/bin/bash
# ========================================
# PoolAIssistant First-Boot Setup Script
# ========================================
# Interactive configuration for a cloned PoolAIssistant Pi
# Run this after flashing a cloned SD card to a new Pi

set -euo pipefail

APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"
ENV_DIR="/etc/PoolAIssistant"
MARKER_FILE="$DATA_DIR/FIRST_BOOT"
PRECONFIG_MARKER="$DATA_DIR/PRE_CONFIGURED"

# Check if this is a first boot
if [ ! -f "$MARKER_FILE" ] && [ ! -f "$PRECONFIG_MARKER" ]; then
    echo "This is not a first boot. Exiting."
    echo "If you need to reconfigure, remove: $MARKER_FILE"
    exit 0
fi

# Check if pre-configured
if [ -f "$PRECONFIG_MARKER" ]; then
    echo "This Pi was pre-configured before shipping."
    echo "Skipping interactive setup and starting services..."
    sudo rm -f "$PRECONFIG_MARKER"
    sudo rm -f "$MARKER_FILE"

    # Initialize databases
    cd "$APP_DIR"
    source /opt/PoolAIssistant/venv/bin/activate
    python3 -c "from modbus_logger import init_db; init_db()"

    # Remove nginx if installed (Flask runs directly on port 80)
    if dpkg -l nginx 2>/dev/null | grep -q "^ii"; then
        sudo systemctl stop nginx 2>/dev/null || true
        sudo apt-get remove -y --purge nginx nginx-common 2>/dev/null || true
        sudo apt-get autoremove -y 2>/dev/null || true
    fi

    # Start services
    sudo systemctl start poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager

    # Get IP address
    IP_ADDR=$(hostname -I | awk '{print $1}')

    echo "========================================"
    echo "Pre-configured Pi Ready!"
    echo "========================================"
    echo "Access web UI at: http://$IP_ADDR"
    echo
    exit 0
fi

echo "========================================"
echo "PoolAIssistant First-Boot Setup"
echo "========================================"
echo
echo "Welcome! This wizard will configure your PoolAIssistant."
echo

# 1. Prompt for site information
read -p "Site name (e.g., 'Riverside Pool'): " SITE_NAME
read -p "Number of controllers (1-10): " NUM_CONTROLLERS

# Validate number
if ! [[ "$NUM_CONTROLLERS" =~ ^[0-9]+$ ]] || [ "$NUM_CONTROLLERS" -lt 1 ] || [ "$NUM_CONTROLLERS" -gt 10 ]; then
    echo "ERROR: Invalid number of controllers. Must be between 1 and 10."
    exit 1
fi

echo
echo "Configuring $NUM_CONTROLLERS controller(s) for $SITE_NAME..."
echo

# 2. Build controllers array
CONTROLLERS="["
for i in $(seq 1 $NUM_CONTROLLERS); do
    echo "Controller $i of $NUM_CONTROLLERS:"
    read -p "  IP address: " IP
    read -p "  Name (e.g., 'Main Pool', 'Spa'): " NAME
    read -p "  Port [502]: " PORT
    PORT=${PORT:-502}
    read -p "  Pool volume (liters, or leave blank): " VOLUME

    # Validate IP reachable
    echo -n "  Testing connection to $IP... "
    if timeout 3 ping -c 1 "$IP" > /dev/null 2>&1; then
        echo "OK"
    else
        echo "WARNING: Cannot reach $IP"
        read -p "  Continue anyway? (yes/no): " continue_anyway
        if [ "$continue_anyway" != "yes" ]; then
            echo "Setup cancelled."
            exit 1
        fi
    fi

    # Test Modbus connection if pymodbus is available
    if command -v python3 > /dev/null 2>&1; then
        echo -n "  Testing Modbus connection... "
        cd "$APP_DIR"
        if source /opt/PoolAIssistant/venv/bin/activate 2>/dev/null && \
           timeout 5 python3 test_modbus_connection.py --host "$IP" --port "$PORT" > /dev/null 2>&1; then
            echo "OK"
        else
            echo "WARNING: Modbus test failed or timed out"
        fi
    fi

    # Build JSON entry
    if [ $i -gt 1 ]; then
        CONTROLLERS="$CONTROLLERS,"
    fi

    if [ -n "$VOLUME" ]; then
        VOLUME_JSON="$VOLUME"
    else
        VOLUME_JSON="null"
    fi

    CONTROLLERS="$CONTROLLERS
    {
      \"enabled\": true,
      \"host\": \"$IP\",
      \"name\": \"$NAME\",
      \"port\": $PORT,
      \"volume_l\": $VOLUME_JSON
    }"

    echo
done

CONTROLLERS="$CONTROLLERS
  ]"

# 3. Prompt for modbus profile
echo "Modbus profile:"
echo "  1) ezetrol (default)"
echo "  2) bayrol"
echo "  3) dulcopool"
read -p "Select profile [1]: " PROFILE_CHOICE
PROFILE_CHOICE=${PROFILE_CHOICE:-1}

case $PROFILE_CHOICE in
    1) MODBUS_PROFILE="ezetrol" ;;
    2) MODBUS_PROFILE="bayrol" ;;
    3) MODBUS_PROFILE="dulcopool" ;;
    *) MODBUS_PROFILE="ezetrol" ;;
esac

# 4. Ezetrol layout if applicable
EZETROL_LAYOUT="CDAB"
if [ "$MODBUS_PROFILE" = "ezetrol" ]; then
    echo
    echo "Ezetrol byte order (CDAB is standard):"
    echo "  1) CDAB (default)"
    echo "  2) ABCD"
    echo "  3) BADC"
    echo "  4) DCBA"
    read -p "Select layout [1]: " LAYOUT_CHOICE
    LAYOUT_CHOICE=${LAYOUT_CHOICE:-1}

    case $LAYOUT_CHOICE in
        1) EZETROL_LAYOUT="CDAB" ;;
        2) EZETROL_LAYOUT="ABCD" ;;
        3) EZETROL_LAYOUT="BADC" ;;
        4) EZETROL_LAYOUT="DCBA" ;;
        *) EZETROL_LAYOUT="CDAB" ;;
    esac
fi

# 5. Generate settings JSON
echo
echo "Generating settings..."

sudo tee "$DATA_DIR/pooldash_settings.json" > /dev/null <<EOF
{
  "controllers": $CONTROLLERS,
  "modbus_profile": "$MODBUS_PROFILE",
  "ezetrol_layout": "$EZETROL_LAYOUT",
  "maintenance_actions": [
    "Backwash Filter 1",
    "Clean Chlorine Probe",
    "Clean pH Probe",
    "Add Chlorine",
    "Add pH Up",
    "Add pH Down",
    "Custom note"
  ]
}
EOF

# Fix ownership of all data files to poolai user
sudo chown -R poolai:poolai "$DATA_DIR"

# 6. Initialize databases
echo "Initializing databases..."
cd "$APP_DIR"
source /opt/PoolAIssistant/venv/bin/activate
python3 -c "from modbus_logger import init_db; init_db()" || echo "Warning: Could not initialize databases"

# 7. System hardening options
echo
echo "System Configuration Options:"
echo

# 7a. Disable desktop environment
read -p "Disable desktop environment (headless mode)? (yes/no) [yes]: " DISABLE_DESKTOP
DISABLE_DESKTOP=${DISABLE_DESKTOP:-yes}
if [ "$DISABLE_DESKTOP" = "yes" ]; then
    echo "Disabling desktop environment..."
    sudo systemctl set-default multi-user.target
    for dm in lightdm gdm3 sddm; do
        sudo systemctl disable "$dm" 2>/dev/null || true
        sudo systemctl stop "$dm" 2>/dev/null || true
    done
    echo "OK - Desktop disabled (headless mode)"
fi

# 7b. Enable SSH
echo "Enabling SSH for remote access..."
sudo ssh-keygen -A 2>/dev/null || true
sudo systemctl enable ssh
sudo systemctl start ssh
echo "OK - SSH enabled"

# 7c. Enable auto-update timer
echo "Enabling automatic update checks..."
sudo systemctl enable update_check.timer 2>/dev/null || true
sudo systemctl start update_check.timer 2>/dev/null || true
echo "OK - Update timer enabled (checks daily at 3 AM)"

# 7d. Enable auto-provisioning service
echo "Enabling auto-provisioning service..."
sudo systemctl enable poolaissistant_provision.service 2>/dev/null || true
echo "OK - Auto-provisioning enabled"

echo

# 8. Remove first-boot marker
sudo rm -f "$MARKER_FILE"

# 9. Remove nginx if installed (Flask runs directly on port 80)
echo "Removing nginx (if installed)..."
if dpkg -l nginx 2>/dev/null | grep -q "^ii"; then
    sudo systemctl stop nginx 2>/dev/null || true
    sudo apt-get remove -y --purge nginx nginx-common 2>/dev/null || true
    sudo apt-get autoremove -y 2>/dev/null || true
    echo "OK - nginx removed"
else
    echo "OK - nginx not installed"
fi

# 10. Check for and apply updates on first boot
echo "Checking for software updates..."
if [ -f "$APP_DIR/scripts/update_check.py" ]; then
    cd "$APP_DIR"
    source /opt/PoolAIssistant/venv/bin/activate
    # Run update check with --apply flag (automatic, no confirmation needed)
    if sudo python3 scripts/update_check.py --apply 2>&1; then
        echo "OK - Update check complete"
    else
        echo "Warning: Update check failed (continuing anyway)"
    fi
else
    echo "Warning: update_check.py not found"
fi

# 11. Start services
echo "Starting PoolAIssistant services..."
sudo systemctl start poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager
sleep 3

# 12. Check service status
echo
echo "Checking service status..."
if sudo systemctl is-active --quiet poolaissistant_logger; then
    echo "  Logger: Running"
else
    echo "  Logger: FAILED - check: journalctl -u poolaissistant_logger -n 50"
fi

if sudo systemctl is-active --quiet poolaissistant_ui; then
    echo "  Web UI: Running"
else
    echo "  Web UI: FAILED - check: journalctl -u poolaissistant_ui -n 50"
fi

if sudo systemctl is-active --quiet poolaissistant_ap_manager; then
    echo "  AP Manager: Running"
else
    echo "  AP Manager: FAILED - check: journalctl -u poolaissistant_ap_manager -n 50"
fi

# 13. Set unique hostname based on device_id
echo "Setting unique hostname..."
# Wait for auto-provisioning to complete and get device_id
sleep 5
DEVICE_ID=$(python3 -c "import json; print(json.load(open('$DATA_DIR/pooldash_settings.json')).get('device_id', ''))" 2>/dev/null || echo "")
if [ -n "$DEVICE_ID" ] && [ ${#DEVICE_ID} -ge 2 ]; then
    # Use last 2 characters of device_id
    SUFFIX="${DEVICE_ID: -2}"
    NEW_HOSTNAME="PoolAI-${SUFFIX}"
else
    # Fallback to random 2 chars
    SUFFIX=$(head /dev/urandom | tr -dc 'a-f0-9' | head -c 2)
    NEW_HOSTNAME="PoolAI-${SUFFIX}"
fi
sudo hostnamectl set-hostname "$NEW_HOSTNAME"
echo "$NEW_HOSTNAME" | sudo tee /etc/hostname > /dev/null
sudo sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$NEW_HOSTNAME/" /etc/hosts
# Update settings with device_name
python3 -c "
import json
settings_path = '$DATA_DIR/pooldash_settings.json'
with open(settings_path, 'r') as f:
    settings = json.load(f)
settings['device_name'] = '$SUFFIX'
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
" 2>/dev/null || true
sudo systemctl restart avahi-daemon 2>/dev/null || true
echo "OK - Hostname set to $NEW_HOSTNAME (access via $NEW_HOSTNAME.local)"

# 14. Display access information
IP_ADDR=$(hostname -I | awk '{print $1}')

echo
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo
echo "Site: $SITE_NAME"
echo "Controllers: $NUM_CONTROLLERS"
echo "Modbus Profile: $MODBUS_PROFILE"
echo
echo "Access web UI at:"
echo "  http://$IP_ADDR"
echo
echo "Monitor logs:"
echo "  journalctl -u poolaissistant_logger -f"
echo "  journalctl -u poolaissistant_ui -f"
echo
echo "Settings file:"
echo "  $DATA_DIR/pooldash_settings.json"
echo
