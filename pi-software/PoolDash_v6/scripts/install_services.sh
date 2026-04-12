#!/bin/bash
# Copyright Ben Salmon 2026. All Rights Reserved.
# PoolAIssistant - Service Installation Script

set -e

SCRIPT_DIR="/opt/PoolAIssistant/app/scripts"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== PoolAIssistant Service Installer ==="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# ============================================
# CRITICAL: Install AP Manager dependencies first
# ============================================
echo "Checking AP Manager dependencies..."
AP_DEPS_MISSING=false

for pkg in hostapd dnsmasq; do
    if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        echo "  -> Missing: $pkg"
        AP_DEPS_MISSING=true
    fi
done

if [ "$AP_DEPS_MISSING" = true ]; then
    echo "Installing missing AP dependencies..."
    apt-get update -qq 2>/dev/null || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq hostapd dnsmasq 2>/dev/null || {
        echo "  WARNING: Could not install some packages"
    }
fi

# Ensure hostapd/dnsmasq don't auto-start (we manage them)
systemctl disable hostapd 2>/dev/null || true
systemctl stop hostapd 2>/dev/null || true
systemctl disable dnsmasq 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true
echo "  -> AP dependencies: OK"
echo

# ============================================
# Install AP Manager service (CRITICAL - provides network fallback)
# ============================================
echo "Installing AP Manager service..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant_ap_manager.service" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant_ap_manager.service" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/poolaissistant_ap_manager.sh" "/usr/local/bin/"
    chmod +x "/usr/local/bin/poolaissistant_ap_manager.sh"

    # Create required directories
    mkdir -p /etc/hostapd /etc/dnsmasq.d 2>/dev/null || true

    systemctl daemon-reload
    systemctl enable poolaissistant_ap_manager.service

    # Start or restart the service
    if systemctl is-active --quiet poolaissistant_ap_manager.service; then
        systemctl restart poolaissistant_ap_manager.service
    else
        systemctl start poolaissistant_ap_manager.service 2>/dev/null || true
    fi

    echo "  -> AP Manager: provides fallback WiFi access point when no network"
else
    echo "  WARNING: AP Manager service file not found!"
fi

# ============================================
# Install Port Configuration service (ensures firewall allows web UI)
# ============================================
echo "Installing port configuration service..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant_ports.service" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant_ports.service" "$SYSTEMD_DIR/"
    chmod +x "$SCRIPT_DIR/ensure_ports.sh"
    systemctl daemon-reload
    systemctl enable poolaissistant_ports.service
    # Run it now to ensure ports are open
    "$SCRIPT_DIR/ensure_ports.sh" || true
    echo "  -> Ports: ensures port 80 is accessible for web UI"
else
    echo "  WARNING: Ports service file not found!"
fi

# Install USB storage service
echo "Installing USB storage service..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant_usb_storage.service" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant_usb_storage.service" "$SYSTEMD_DIR/"
    chmod +x "$SCRIPT_DIR/usb_data_mount.sh"
    systemctl daemon-reload
    systemctl enable poolaissistant_usb_storage.service
    echo "  -> USB storage: auto-detects USB for data storage on boot"
fi

# Install auto-provisioning service
echo "Installing auto-provisioning service..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant_provision.service" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant_provision.service" "$SYSTEMD_DIR/"
    systemctl daemon-reload
    systemctl enable poolaissistant_provision.service
    echo "  -> Auto-provision: runs on boot if not provisioned"
fi

# Install update check timer
echo "Installing update check timer..."
cp "$SCRIPT_DIR/update_check.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/update_check.timer" "$SYSTEMD_DIR/"
systemctl daemon-reload
systemctl enable update_check.timer
systemctl start update_check.timer
echo "  -> Update check: daily at 3 AM"

# Install watchdog timer
echo "Installing watchdog timer..."
cp "$SCRIPT_DIR/watchdog.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/watchdog.timer" "$SYSTEMD_DIR/"
systemctl daemon-reload
systemctl enable watchdog.timer
systemctl start watchdog.timer
echo "  -> Watchdog: every 5 minutes"

# Install settings backup timer
echo "Installing settings backup timer..."
cp "$SCRIPT_DIR/settings_backup.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/settings_backup.timer" "$SYSTEMD_DIR/"
systemctl daemon-reload
systemctl enable settings_backup.timer
systemctl start settings_backup.timer
echo "  -> Settings backup: daily at 4 AM"

# Install chunk sync timer
echo "Installing chunk sync timer..."
cp "$SCRIPT_DIR/chunk_sync.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/chunk_sync.timer" "$SYSTEMD_DIR/"
systemctl daemon-reload
systemctl enable chunk_sync.timer
systemctl start chunk_sync.timer
echo "  -> Chunk sync: every 6 hours"

# Install log rotation
echo "Installing log rotation..."
if [ -f "$SCRIPT_DIR/poolaissistant-logrotate" ]; then
    cp "$SCRIPT_DIR/poolaissistant-logrotate" "/etc/logrotate.d/poolaissistant"
    echo "  -> Log rotation: daily, 7 day retention"
fi

# Create data directories
echo "Creating data directories..."
mkdir -p /opt/PoolAIssistant/data/chunks
mkdir -p /opt/PoolAIssistant/data/updates
chown -R poolaissistant:poolaissistant /opt/PoolAIssistant/data 2>/dev/null || true

# Optimize database if it exists
if [ -f "/opt/PoolAIssistant/data/pool_readings.sqlite3" ]; then
    echo "Optimizing database..."
    python3 "$SCRIPT_DIR/db_optimize.py" || true
fi

echo
echo "=== Installation Complete ==="
echo
echo "Active timers:"
systemctl list-timers --no-pager | grep -E "(update_check|watchdog|settings_backup|chunk_sync)" || echo "  (none found - check systemctl status)"
echo
echo "To check status:"
echo "  systemctl status update_check.timer"
echo "  systemctl status watchdog.timer"
echo "  systemctl status settings_backup.timer"
