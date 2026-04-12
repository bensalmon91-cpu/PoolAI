#!/bin/bash
# ========================================
# PoolAIssistant Clone Preparation Script (SAFE VERSION)
# ========================================
# Prepares a PoolAIssistant Pi for SD card cloning
#
# IMPORTANT: This script should be run LOCALLY on the Pi with
# a monitor and keyboard attached, NOT over SSH!
#
# Key features:
# 1. Network-breaking operations happen LAST
# 2. SSH keys backed up and auto-restored on boot
# 3. All services properly enabled
# 4. Ethernet reset to DHCP
# 5. AP config reset to defaults

set -euo pipefail

APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"
SYSTEM_DIR="/opt/PoolAIssistant/system"  # Protected from data wipes
INSTANCE_DIR="/opt/PoolAIssistant/app/instance"

echo "========================================"
echo "PoolAIssistant Clone Preparation (SAFE)"
echo "========================================"
echo
echo "WARNING: This script should be run LOCALLY"
echo "on the Pi with a monitor+keyboard, NOT over SSH!"
echo
echo "This will:"
echo "  - Stop all PoolAIssistant services"
echo "  - Delete all databases and user data"
echo "  - Reset settings to template"
echo "  - Reset ethernet to DHCP"
echo "  - Reset AP to defaults (SSID: PoolAI)"
echo "  - Create first-boot marker"
echo "  - Clean logs"
echo "  - Remove WiFi networks (LAST)"
echo "  - Remove SSH host keys (LAST, but preserve access)"
echo
read -p "Are you running this LOCALLY (not over SSH)? (yes/no): " local_confirm
if [ "$local_confirm" != "yes" ]; then
    echo "ABORTED: Please run this script locally on the Pi."
    echo "Connect a monitor and keyboard to the Pi first."
    exit 1
fi
echo
read -p "Continue with clone preparation? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi
echo

# 1. Stop services
echo "[1/15] Stopping PoolAIssistant services..."
sudo systemctl stop poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager poolaissistant_button 2>/dev/null || true
echo "OK - Services stopped"
echo

# 2. Backup SSH authorized_keys to PROTECTED location (survives data wipes)
echo "[2/15] Backing up SSH authorized_keys..."
sudo mkdir -p "$SYSTEM_DIR"
sudo chown poolai:poolai "$SYSTEM_DIR"
if [ -f /home/poolai/.ssh/authorized_keys ]; then
    sudo cp /home/poolai/.ssh/authorized_keys "$SYSTEM_DIR/ssh_authorized_keys_backup"
    sudo chown poolai:poolai "$SYSTEM_DIR/ssh_authorized_keys_backup"
    sudo chmod 600 "$SYSTEM_DIR/ssh_authorized_keys_backup"
    echo "OK - SSH keys backed up to $SYSTEM_DIR/ssh_authorized_keys_backup"
else
    echo "WARN - No authorized_keys found to backup"
fi
echo

# 3. Create SSH restore service (runs on boot to restore authorized_keys)
echo "[3/15] Creating SSH restore service..."
sudo tee /etc/systemd/system/poolaissistant_ssh_restore.service > /dev/null <<'SSHRESTORE'
[Unit]
Description=Restore SSH authorized_keys from backup
After=ssh.service
ConditionPathExists=/opt/PoolAIssistant/system/ssh_authorized_keys_backup

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'mkdir -p /home/poolai/.ssh && chmod 700 /home/poolai/.ssh && cp /opt/PoolAIssistant/system/ssh_authorized_keys_backup /home/poolai/.ssh/authorized_keys && chmod 600 /home/poolai/.ssh/authorized_keys && chown -R poolai:poolai /home/poolai/.ssh'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SSHRESTORE
sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_ssh_restore.service
echo "OK - SSH restore service created and enabled"
echo

# 4. Ensure ALL services are enabled for boot
echo "[4/15] Enabling all services for boot..."
sudo systemctl enable poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager 2>/dev/null || true
sudo systemctl enable poolaissistant_button 2>/dev/null || true
sudo systemctl enable poolaissistant_ssh_restore 2>/dev/null || true
sudo systemctl enable ssh avahi-daemon nginx 2>/dev/null || true
echo "OK - All services enabled"
echo

# 5. Remove databases and status files
echo "[5/15] Removing databases and status files..."
for db in pool_readings.sqlite3 maintenance_logs.sqlite3 alarm_log.sqlite3; do
    if [ -f "$DATA_DIR/$db" ]; then
        sudo rm -f "$DATA_DIR/$db"
        echo "  Removed: $db"
    fi
done
sudo rm -f "$DATA_DIR/boot_status.json" "$DATA_DIR/boot_check.log" "$DATA_DIR/update_status.json"
if [ -d "$INSTANCE_DIR" ]; then
    sudo rm -rf "$INSTANCE_DIR"/*.sqlite3 2>/dev/null || true
    sudo rm -rf "$INSTANCE_DIR"/*.json 2>/dev/null || true
fi
echo "OK - Databases and status files removed"
echo

# 6. Create template settings (persist.py will fill in missing DEFAULTS)
echo "[6/15] Creating template settings..."
sudo mkdir -p "$DATA_DIR"
sudo tee "$DATA_DIR/pooldash_settings.json" > /dev/null <<'EOF'
{
  "controllers": [],
  "modbus_profile": "ezetrol",
  "ezetrol_layout": "CDAB",
  "device_id": "",
  "device_alias": "",
  "remote_sync_enabled": false,
  "remote_api_key": "",
  "data_retention_enabled": true,
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
sudo chown poolai:poolai "$DATA_DIR/pooldash_settings.json" 2>/dev/null || true
echo "OK - Template settings created"
echo

# 7. Create first-boot marker
echo "[7/15] Creating first-boot marker..."
sudo touch "$DATA_DIR/FIRST_BOOT"
sudo touch "/opt/PoolAIssistant/FIRST_BOOT"
echo "OK - First-boot marker created"
echo

# 8. Clean logs
echo "[8/15] Cleaning logs..."
sudo journalctl --rotate 2>/dev/null || true
sudo journalctl --vacuum-time=1s 2>/dev/null || true
sudo rm -f /var/log/poolaissistant*.log 2>/dev/null || true
echo "OK - Logs cleaned"
echo

# 9. Clean bash history
echo "[9/15] Cleaning bash history..."
history -c 2>/dev/null || true
cat /dev/null > ~/.bash_history 2>/dev/null || true
sudo cat /dev/null > /root/.bash_history 2>/dev/null || true
echo "OK - History cleaned"
echo

# 10. Reset machine-id
echo "[10/15] Resetting machine-id..."
sudo truncate -s 0 /etc/machine-id 2>/dev/null || true
sudo rm -f /var/lib/dbus/machine-id 2>/dev/null || true
echo "OK - Machine ID will regenerate on first boot"
echo

# 11. Set hostname and enable mDNS
echo "[11/15] Setting hostname and enabling mDNS..."
sudo hostnamectl set-hostname poolaissistant
echo "poolaissistant" | sudo tee /etc/hostname > /dev/null
sudo sed -i 's/127\.0\.1\.1.*/127.0.1.1\tpoolaissistant/' /etc/hosts
sudo systemctl enable avahi-daemon 2>/dev/null || true
echo "OK - Hostname set to 'poolaissistant'"
echo

# 12. Reset ethernet to DHCP
echo "[12/15] Resetting ethernet to DHCP..."
if command -v nmcli &> /dev/null; then
    # Find ethernet connection and reset to DHCP
    ETH_CON=$(nmcli -t -f NAME,TYPE con show | grep ":ethernet$" | head -1 | cut -d: -f1)
    if [ -n "$ETH_CON" ]; then
        sudo nmcli con mod "$ETH_CON" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns "" 2>/dev/null || true
        echo "  Reset '$ETH_CON' to DHCP"
    fi
fi
echo "OK - Ethernet reset to DHCP"
echo

# 13. Reset AP/hostapd to defaults
echo "[13/15] Resetting Access Point to defaults..."
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
if [ -d "/etc/hostapd" ]; then
    sudo tee "$HOSTAPD_CONF" > /dev/null <<'APCONF'
interface=wlan0
driver=nl80211
ssid=PoolAI
hw_mode=g
channel=6
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=12345678
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
APCONF
    sudo chmod 600 "$HOSTAPD_CONF"
    echo "  Reset hostapd.conf (SSID: PoolAI, Pass: 12345678)"
fi

DNSMASQ_CONF="/etc/dnsmasq.d/poolaissistant.conf"
sudo mkdir -p /etc/dnsmasq.d

# Ensure main dnsmasq.conf reads drop-in configs (often commented out by default)
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

sudo tee "$DNSMASQ_CONF" > /dev/null <<'DNSCONF'
# PoolAIssistant AP DHCP/DNS config
interface=wlan0
bind-interfaces
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
no-resolv

# Local DNS
address=/poolai.local/192.168.4.1
address=/poolaissistant.local/192.168.4.1
address=/setup.local/192.168.4.1

# Captive portal redirects (helps phones connect)
address=/captive.apple.com/192.168.4.1
address=/www.apple.com/192.168.4.1
address=/connectivitycheck.gstatic.com/192.168.4.1
address=/clients3.google.com/192.168.4.1
address=/detectportal.firefox.com/192.168.4.1

domain-needed
bogus-priv

# DHCP options
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
DNSCONF
echo "  Reset dnsmasq config (with captive portal support)"
echo "OK - AP reset to defaults"
echo

# 14. Configure SSH for recovery (BEFORE removing keys)
echo "[14/15] Configuring SSH for recovery..."

# Ensure password auth is enabled
SSHD_CONFIG="/etc/ssh/sshd_config"
if [ -f "$SSHD_CONFIG" ]; then
    sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
    sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$SSHD_CONFIG"
    sudo sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' "$SSHD_CONFIG"
    echo "  SSH config updated (password + pubkey auth enabled)"
fi

# Create SSH key regeneration service
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
echo "OK - SSH recovery configured"
echo

# ==== NETWORK-BREAKING OPERATIONS LAST ====

echo "[15/15] Final cleanup (network will be disrupted)..."
echo

# 15a. Forget WiFi networks
echo "  Forgetting WiFi networks..."
if command -v nmcli &> /dev/null; then
    for conn in $(nmcli -t -f NAME,TYPE con show | grep ":wifi$" | cut -d: -f1); do
        sudo nmcli con delete "$conn" 2>/dev/null || true
        echo "    Deleted: $conn"
    done
fi

# Also clear wpa_supplicant (detect country from existing config or default to GB)
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
if [ -f "$WPA_CONF" ]; then
    # Try to preserve existing country code
    COUNTRY=$(grep -oP '(?<=country=)[A-Z]{2}' "$WPA_CONF" 2>/dev/null || echo "GB")
    sudo tee "$WPA_CONF" > /dev/null <<WPAEOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=$COUNTRY
WPAEOF
    sudo chmod 600 "$WPA_CONF"
    echo "  Cleared wpa_supplicant (country: $COUNTRY)"
fi
echo "  OK - WiFi networks cleared"

# 15b. Remove SSH host keys (regenerate on first boot)
echo "  Removing SSH host keys..."
sudo rm -f /etc/ssh/ssh_host_*
echo "  OK - SSH host keys removed (will regenerate on boot)"

echo
echo "========================================"
echo "Clone Preparation Complete!"
echo "========================================"
echo
echo "The Pi is ready for SD card imaging."
echo
echo "IMPORTANT - After cloning:"
echo "  - SSH host keys regenerate automatically on boot"
echo "  - SSH authorized_keys restored from: $SYSTEM_DIR/"
echo "  - Password auth enabled (user: poolai, pass: 12345678)"
echo "  - AP available: SSID 'PoolAI', pass '12345678'"
echo "  - Ethernet: DHCP (auto IP)"
echo "  - Physical reset button: GPIO3 (Pin 5)"
echo
echo "Next steps:"
echo "1. Shut down the Pi:"
echo "   sudo shutdown -h now"
echo
echo "2. Remove SD card and create image"
echo
echo "3. Flash image to new SD cards for deployment"
echo
