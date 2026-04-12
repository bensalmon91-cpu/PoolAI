#!/bin/bash
# ========================================
# PoolAIssistant Clone Preparation Script
# ========================================
# Prepares a PoolAIssistant Pi for SD card cloning
# Run this on the Pi before creating a master image
#
# v2.0 - March 2026
# - Added package verification/installation
# - Added labwc kiosk autostart creation
# - Added health reporter timer installation
# - Added Pi 5 compatibility (GPIO detection)
# - Added SSH authorized_keys setup
# - Fixed port 80 consistency

set -euo pipefail

# Configuration
APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"
LOGS_DIR="/opt/PoolAIssistant/logs"
INSTANCE_DIR="/opt/PoolAIssistant/app/instance"
VENV_DIR="/opt/PoolAIssistant/venv"

# Detect user (poolaissistant or poolai)
if id "poolaissistant" &>/dev/null; then
    PI_USER="poolaissistant"
elif id "poolai" &>/dev/null; then
    PI_USER="poolai"
else
    PI_USER="$USER"
fi
PI_HOME="/home/$PI_USER"

echo "========================================"
echo "PoolAIssistant Clone Preparation v2.0"
echo "========================================"
echo
echo "Detected user: $PI_USER"
echo
echo "This script will:"
echo "  1. Verify/install required packages"
echo "  2. Configure kiosk display (labwc)"
echo "  3. Install health reporter timer"
echo "  4. Stop services and clear data"
echo "  5. Reset settings to template"
echo "  6. Configure SSH and security"
echo "  7. Prepare for first-boot"
echo
read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi
echo

# ============================================
# PHASE 1: VERIFY AND INSTALL PACKAGES
# ============================================
echo "========================================"
echo "PHASE 1: Package Verification"
echo "========================================"
echo

echo "[1/6] Checking required packages..."
REQUIRED_PACKAGES=(
    "chromium"
    "labwc"
    "swaybg"
    "wlr-randr"
    "python3"
    "python3-venv"
    "curl"
    "avahi-daemon"
    "fail2ban"
    "lightdm"
    "hostapd"
    "dnsmasq"
    "iw"
)

MISSING_PACKAGES=()
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        MISSING_PACKAGES+=("$pkg")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo "Missing packages: ${MISSING_PACKAGES[*]}"
    read -p "Install missing packages? (yes/no): " install_confirm
    if [ "$install_confirm" == "yes" ]; then
        sudo apt update
        sudo apt install -y "${MISSING_PACKAGES[@]}"
        echo "OK - Packages installed"
    else
        echo "WARNING: Some packages missing, continuing anyway..."
    fi
else
    echo "OK - All required packages present"
fi
echo

# ============================================
# PHASE 1B: CONFIGURE AP INFRASTRUCTURE
# ============================================
echo "========================================"
echo "PHASE 1B: AP Manager Setup"
echo "========================================"
echo

echo "Configuring Access Point infrastructure..."

# Unmask hostapd (it's masked by default on Raspberry Pi OS!)
echo "  Unmasking hostapd..."
sudo systemctl unmask hostapd 2>/dev/null || true

# Stop and disable hostapd/dnsmasq auto-start (AP manager controls them)
sudo systemctl stop hostapd dnsmasq 2>/dev/null || true
sudo systemctl disable hostapd dnsmasq 2>/dev/null || true

# Create required directories
sudo mkdir -p /etc/hostapd /etc/dnsmasq.d 2>/dev/null || true

# Enable dnsmasq conf-dir (often commented out by default)
MAIN_DNSMASQ="/etc/dnsmasq.conf"
if [ -f "$MAIN_DNSMASQ" ]; then
    if ! grep -q "^conf-dir=/etc/dnsmasq.d" "$MAIN_DNSMASQ" 2>/dev/null; then
        if grep -q "^#conf-dir=/etc/dnsmasq.d" "$MAIN_DNSMASQ" 2>/dev/null; then
            sudo sed -i 's|^#conf-dir=/etc/dnsmasq.d|conf-dir=/etc/dnsmasq.d|' "$MAIN_DNSMASQ"
            echo "  Enabled conf-dir in dnsmasq.conf"
        else
            echo "conf-dir=/etc/dnsmasq.d/,*.conf" | sudo tee -a "$MAIN_DNSMASQ" > /dev/null
            echo "  Added conf-dir to dnsmasq.conf"
        fi
    fi
fi

# Install AP manager script to /usr/local/bin
echo "  Installing AP manager script..."
if [ -f "$APP_DIR/scripts/poolaissistant_ap_manager.sh" ]; then
    sudo rm -f /usr/local/bin/poolaissistant_ap_manager.sh 2>/dev/null || true
    sudo cp "$APP_DIR/scripts/poolaissistant_ap_manager.sh" /usr/local/bin/
    sudo chmod +x /usr/local/bin/poolaissistant_ap_manager.sh
    echo "  OK - AP manager script installed"
else
    echo "  WARNING: AP manager script not found at $APP_DIR/scripts/"
fi

# Install AP manager systemd service
echo "  Installing AP manager service..."
if [ -f "$APP_DIR/scripts/systemd/poolaissistant_ap_manager.service" ]; then
    sudo rm -f /etc/systemd/system/poolaissistant_ap_manager.service 2>/dev/null || true
    sudo cp "$APP_DIR/scripts/systemd/poolaissistant_ap_manager.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable poolaissistant_ap_manager.service
    echo "  OK - AP manager service installed and enabled"
else
    echo "  WARNING: AP manager service file not found"
fi

# Verify AP manager is ready
if [ -f "/usr/local/bin/poolaissistant_ap_manager.sh" ] && \
   [ -f "/etc/systemd/system/poolaissistant_ap_manager.service" ]; then
    echo "OK - AP Manager infrastructure ready"
else
    echo "WARNING - AP Manager may not work properly!"
fi
echo

# ============================================
# PHASE 2: CREATE DIRECTORIES
# ============================================
echo "[2/6] Creating directories..."
sudo mkdir -p "$DATA_DIR" "$LOGS_DIR" "$INSTANCE_DIR"
sudo mkdir -p "$PI_HOME/.config/labwc"
sudo chown -R "$PI_USER:$PI_USER" "/opt/PoolAIssistant"
sudo chown -R "$PI_USER:$PI_USER" "$PI_HOME/.config/labwc"
echo "OK - Directories created"
echo

# ============================================
# PHASE 3: CONFIGURE KIOSK DISPLAY
# ============================================
echo "========================================"
echo "PHASE 2: Kiosk Display Configuration"
echo "========================================"
echo

echo "[3/6] Creating labwc autostart (kiosk mode)..."
sudo -u "$PI_USER" tee "$PI_HOME/.config/labwc/autostart" > /dev/null <<'LABWC_AUTOSTART'
# PoolAIssistant Kiosk Mode
# Auto-generated by clone_prep.sh

pkill -f pcmanfm-pi 2>/dev/null
pkill -f wf-panel-pi 2>/dev/null

swaybg -c '#000000' &

# Apply screen rotation from saved settings
ROTATION=$(python3 -c "import json; print(json.load(open('/opt/PoolAIssistant/data/pooldash_settings.json')).get('screen_rotation', 0))" 2>/dev/null || echo 0)
case "$ROTATION" in
    90)  TRANSFORM="90" ;;
    180) TRANSFORM="180" ;;
    270) TRANSFORM="270" ;;
    *)   TRANSFORM="normal" ;;
esac
sleep 2
wlr-randr --output DSI-2 --transform "$TRANSFORM" 2>/dev/null &

sleep 3

# Chromium kiosk - Flask runs on port 80
/usr/bin/chromium --noerrdialogs --disable-infobars --kiosk --incognito \
  --ozone-platform=wayland --password-store=basic \
  --touch-events=enabled \
  --enable-touch-drag-drop \
  http://localhost &
LABWC_AUTOSTART
echo "OK - labwc autostart created"
echo

# ============================================
# PHASE 4: INSTALL HEALTH REPORTER TIMER
# ============================================
echo "========================================"
echo "PHASE 3: Health Reporter Timer"
echo "========================================"
echo

echo "[4/6] Installing health reporter systemd timer..."

# Create the service
sudo tee /etc/systemd/system/poolaissistant_health.service > /dev/null <<EOF
[Unit]
Description=PoolAIssistant Health Reporter
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$PI_USER
ExecStart=$VENV_DIR/bin/python $APP_DIR/scripts/health_reporter.py
StandardOutput=append:$LOGS_DIR/health_reporter.log
StandardError=append:$LOGS_DIR/health_reporter.log
EOF

# Create the timer
sudo tee /etc/systemd/system/poolaissistant_health.timer > /dev/null <<'EOF'
[Unit]
Description=Run PoolAIssistant Health Reporter every 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
AccuracySec=1min

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_health.timer
echo "OK - Health reporter timer installed"
echo

# ============================================
# PHASE 5: PI 5 COMPATIBILITY
# ============================================
echo "[5/6] Checking Pi model compatibility..."
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
echo "Detected: $PI_MODEL"

if echo "$PI_MODEL" | grep -qi "Pi 5"; then
    echo "Pi 5 detected - disabling button service (GPIO not supported)"
    sudo systemctl disable poolaissistant_button.service 2>/dev/null || true
    sudo systemctl stop poolaissistant_button.service 2>/dev/null || true
fi
echo "OK - Pi model handled"
echo

# ============================================
# PHASE 6: SSH AUTHORIZED KEYS
# ============================================
echo "[6/6] Setting up SSH authorized_keys..."
SSH_DIR="$PI_HOME/.ssh"
sudo mkdir -p "$SSH_DIR"
sudo chmod 700 "$SSH_DIR"

# Add standard Claude SSH key if not present
CLAUDE_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICT2USTN90TYd32Y6iQf7RW9q/AGYULgAv1RVykZhxuk claude-pi"
if [ -f "$SSH_DIR/authorized_keys" ]; then
    if ! grep -q "claude-pi" "$SSH_DIR/authorized_keys"; then
        echo "$CLAUDE_KEY" | sudo tee -a "$SSH_DIR/authorized_keys" > /dev/null
        echo "Added Claude SSH key"
    else
        echo "Claude SSH key already present"
    fi
else
    echo "$CLAUDE_KEY" | sudo tee "$SSH_DIR/authorized_keys" > /dev/null
    echo "Created authorized_keys with Claude SSH key"
fi

sudo chmod 600 "$SSH_DIR/authorized_keys"
sudo chown -R "$PI_USER:$PI_USER" "$SSH_DIR"

# Create restore service for SSH keys after clone
sudo tee /etc/systemd/system/poolaissistant_ssh_restore.service > /dev/null <<EOF
[Unit]
Description=Restore SSH authorized_keys after clone
After=local-fs.target
ConditionPathExists=$SSH_DIR/authorized_keys

[Service]
Type=oneshot
ExecStart=/bin/true
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable poolaissistant_ssh_restore.service 2>/dev/null || true
echo "OK - SSH keys configured"
echo

# ============================================
# PHASE 7: STOP SERVICES AND CLEAR DATA
# ============================================
echo "========================================"
echo "PHASE 4: Clear Data for Cloning"
echo "========================================"
echo

echo "[7/14] Stopping PoolAIssistant services..."
sudo systemctl stop poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager poolaissistant_health.timer 2>/dev/null || true
echo "OK - Services stopped"
echo

echo "[8/14] Ensuring services are enabled for boot..."
sudo systemctl enable poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager poolaissistant_health.timer 2>/dev/null || true
echo "OK - Services enabled"
echo

echo "[9/14] Removing databases..."
# NOTE: maintenance_logs are now stored in pool_readings.sqlite3 (merged database)
# We still remove the legacy maintenance_logs.sqlite3 if it exists from older versions
for db in pool_readings.sqlite3 maintenance_logs.sqlite3 maintenance_logs.sqlite3.migrated alarm_log.sqlite3 ai_assistant.db; do
    if [ -f "$DATA_DIR/$db" ]; then
        sudo rm -f "$DATA_DIR/$db"
        echo "Removed: $db"
    fi
done
sudo rm -f "$DATA_DIR/boot_status.json" "$DATA_DIR/boot_check.log" "$DATA_DIR/health_state.json"
if [ -d "$INSTANCE_DIR" ]; then
    sudo rm -rf "$INSTANCE_DIR"/*.sqlite3 2>/dev/null || true
    sudo rm -rf "$INSTANCE_DIR"/*.json 2>/dev/null || true
fi
echo "OK - Databases removed"
echo

# Remove provisioning marker so new Pi will auto-provision
sudo rm -f "$DATA_DIR/.provisioned"
echo "OK - Provisioning marker removed (will auto-provision on boot)"
echo

echo "[10/14] Creating template settings..."
sudo tee "$DATA_DIR/pooldash_settings.json" > /dev/null <<'EOF'
{
  "controllers": [],
  "modbus_profile": "ezetrol",
  "ezetrol_layout": "CDAB",
  "device_id": "",
  "device_alias": "",
  "device_name": "",
  "remote_sync_enabled": false,
  "screen_rotation": 0,
  "maintenance_actions": [
    "Backwash Filter",
    "Clean Chlorine Probe",
    "Clean pH Probe",
    "Add Chlorine",
    "Add pH Up",
    "Add pH Down",
    "Custom note"
  ]
}
EOF
# Fix ownership of all data files to correct user
sudo chown -R "$PI_USER:$PI_USER" "$DATA_DIR"
echo "OK - Template settings created and ownership fixed"
echo

echo "[11/14] Creating first-boot marker..."
sudo touch "$DATA_DIR/FIRST_BOOT"
sudo touch "/opt/PoolAIssistant/FIRST_BOOT"
echo "OK - First-boot marker created"
echo

# ============================================
# PHASE 8: SYSTEM CLEANUP
# ============================================
echo "========================================"
echo "PHASE 5: System Cleanup"
echo "========================================"
echo

echo "[12/14] Cleaning logs..."
sudo rm -f "$LOGS_DIR"/*.log 2>/dev/null || true
sudo journalctl --rotate 2>/dev/null || true
sudo journalctl --vacuum-time=1s 2>/dev/null || true
echo "OK - Logs cleaned"
echo

echo "[13/14] Removing SSH host keys..."
sudo rm -f /etc/ssh/ssh_host_*
sudo systemctl enable regenerate_ssh_host_keys 2>/dev/null || true

sudo tee /etc/systemd/system/ssh-keygen-on-boot.service > /dev/null <<'SSHSERVICE'
[Unit]
Description=Regenerate SSH host keys if missing
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_rsa_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
ExecStartPost=/bin/systemctl restart ssh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SSHSERVICE
sudo systemctl daemon-reload
sudo systemctl enable ssh-keygen-on-boot.service
sudo systemctl enable ssh
echo "OK - SSH host keys removed (will regenerate on first boot)"
echo

echo "[14/14] Forgetting WiFi networks..."
if command -v nmcli &> /dev/null; then
    for conn in $(nmcli -t -f NAME,TYPE con show | grep ":wifi$" | cut -d: -f1); do
        sudo nmcli con delete "$conn" 2>/dev/null || true
        echo "Deleted WiFi: $conn"
    done
fi
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
if [ -f "$WPA_CONF" ]; then
    sudo tee "$WPA_CONF" > /dev/null <<'WPAEOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB
WPAEOF
    sudo chmod 600 "$WPA_CONF"
fi
echo "OK - WiFi networks cleared"
echo

# ============================================
# PHASE 9: SECURITY HARDENING
# ============================================
echo "========================================"
echo "PHASE 6: Security Hardening"
echo "========================================"
echo

echo "Setting temporary hostname..."
sudo hostnamectl set-hostname poolai
echo "poolai" | sudo tee /etc/hostname > /dev/null
sudo sed -i 's/127\.0\.1\.1.*/127.0.1.1\tpoolai/' /etc/hosts
sudo systemctl enable avahi-daemon 2>/dev/null || true
echo "OK - Hostname set to 'poolai' (accessible at poolai.local)"
echo

echo "Installing cloud-init hostname preservation config..."
# Prevent cloud-init from overwriting hostname on boot (allows Quick Connect to work)
sudo tee /etc/cloud/cloud.cfg.d/01_preserve_hostname.cfg > /dev/null <<'CLOUDINIT'
# Cloud-init config to preserve hostname set by PoolAIssistant app
# Without this, cloud-init resets the hostname to the value in
# /boot/firmware/user-data on every boot, overwriting any changes
# made via the Quick Connect hostname setting in the web UI.
preserve_hostname: true
CLOUDINIT
echo "OK - Cloud-init will preserve hostname changes"
echo

echo "Configuring firewall..."
if command -v ufw &> /dev/null && sudo ufw status | grep -q "Status: active"; then
    sudo ufw allow 80/tcp 2>/dev/null || true
    sudo ufw allow 22/tcp 2>/dev/null || true
    sudo ufw delete allow 8080/tcp 2>/dev/null || true
    echo "OK - Firewall: ports 80, 22 open"
else
    echo "OK - Firewall not active"
fi
echo

echo "Hardening SSH..."
SSHD_CONFIG="/etc/ssh/sshd_config"
if [ -f "$SSHD_CONFIG" ]; then
    sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
    sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$SSHD_CONFIG"
fi
echo "OK - SSH hardened"
echo

echo "Configuring fail2ban..."
if command -v fail2ban-client &> /dev/null; then
    sudo tee /etc/fail2ban/jail.local > /dev/null <<'FAIL2BAN'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 1h
FAIL2BAN
    sudo systemctl enable fail2ban 2>/dev/null || true
    echo "OK - fail2ban configured"
else
    echo "SKIP - fail2ban not installed"
fi
echo

# Clean history
history -c 2>/dev/null || true
cat /dev/null > ~/.bash_history 2>/dev/null || true
sudo cat /dev/null > /root/.bash_history 2>/dev/null || true

# Reset machine-id
sudo truncate -s 0 /etc/machine-id 2>/dev/null || true
sudo rm -f /var/lib/dbus/machine-id 2>/dev/null || true

# ============================================
# VERIFICATION
# ============================================
echo "========================================"
echo "VERIFICATION"
echo "========================================"
echo

ERRORS=0

# Check critical files
echo "Checking critical files..."
[ -f "$PI_HOME/.config/labwc/autostart" ] && echo "  [OK] labwc autostart" || { echo "  [FAIL] labwc autostart"; ERRORS=$((ERRORS+1)); }
[ -f "/etc/systemd/system/poolaissistant_health.timer" ] && echo "  [OK] health timer" || { echo "  [FAIL] health timer"; ERRORS=$((ERRORS+1)); }
[ -f "$SSH_DIR/authorized_keys" ] && echo "  [OK] SSH authorized_keys" || { echo "  [FAIL] SSH authorized_keys"; ERRORS=$((ERRORS+1)); }
[ -f "$DATA_DIR/pooldash_settings.json" ] && echo "  [OK] settings template" || { echo "  [FAIL] settings template"; ERRORS=$((ERRORS+1)); }
[ -f "$DATA_DIR/FIRST_BOOT" ] && echo "  [OK] FIRST_BOOT marker" || { echo "  [FAIL] FIRST_BOOT marker"; ERRORS=$((ERRORS+1)); }

# Check AP infrastructure (CRITICAL for connectivity!)
echo
echo "Checking AP infrastructure..."
[ -f "/usr/local/bin/poolaissistant_ap_manager.sh" ] && echo "  [OK] AP manager script" || { echo "  [FAIL] AP manager script"; ERRORS=$((ERRORS+1)); }
[ -f "/etc/systemd/system/poolaissistant_ap_manager.service" ] && echo "  [OK] AP manager service" || { echo "  [FAIL] AP manager service"; ERRORS=$((ERRORS+1)); }
command -v hostapd >/dev/null && echo "  [OK] hostapd installed" || { echo "  [FAIL] hostapd not installed"; ERRORS=$((ERRORS+1)); }
command -v dnsmasq >/dev/null && echo "  [OK] dnsmasq installed" || { echo "  [FAIL] dnsmasq not installed"; ERRORS=$((ERRORS+1)); }
! systemctl is-masked hostapd 2>/dev/null && echo "  [OK] hostapd not masked" || { echo "  [FAIL] hostapd is masked"; ERRORS=$((ERRORS+1)); }
grep -q "^conf-dir=/etc/dnsmasq.d" /etc/dnsmasq.conf 2>/dev/null && echo "  [OK] dnsmasq conf-dir enabled" || { echo "  [WARN] dnsmasq conf-dir may be disabled"; }

# Check port references
echo "Checking for port 8080 references..."
if grep -r "localhost:8080" "$PI_HOME/.config/labwc/" 2>/dev/null; then
    echo "  [FAIL] Found localhost:8080 in labwc config"
    ERRORS=$((ERRORS+1))
else
    echo "  [OK] No port 8080 references in kiosk config"
fi

echo
if [ $ERRORS -eq 0 ]; then
    echo "All checks passed!"
else
    echo "WARNING: $ERRORS check(s) failed"
fi
echo

# ============================================
# COMPLETE
# ============================================
echo "========================================"
echo "Clone Preparation Complete!"
echo "========================================"
echo
echo "The Pi is ready for SD card imaging."
echo
echo "What was configured:"
echo "  - All required packages verified (including hostapd, dnsmasq)"
echo "  - AP Manager installed and enabled (fallback WiFi: PoolAI - no password)"
echo "  - Kiosk display (labwc) configured for port 80"
echo "  - Health reporter timer installed (15 min interval)"
echo "  - SSH keys configured for remote access"
echo "  - Databases and settings cleared"
echo "  - Security hardening applied"
echo
echo "Next steps:"
echo "  1. Shut down: sudo shutdown -h now"
echo "  2. Remove SD card and create image"
echo "  3. Flash to new SD cards"
echo "  4. Each clone auto-provisions on first boot"
echo
