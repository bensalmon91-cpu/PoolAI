#!/bin/bash
# Copyright Ben Salmon 2026. All Rights Reserved.
# PoolAIssistant - Service Installation Script

set -e

SCRIPT_DIR="/opt/PoolAIssistant/app/scripts"
SYSTEMD_DIR="/etc/systemd/system"

# Names of components skipped because their unit/script wasn't on disk. Surfaced
# in the post-install summary so a non-interactive deploy run notices the gap
# (which previously only emitted a stdout "WARNING:" line — easy to miss).
SKIPPED_COMPONENTS=()

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
# AP Manager daemon: DISABLED.
# The old poolaissistant_ap_manager.service auto-started an AP whenever
# it thought the network was down, but its 10s polling raced against
# NetworkManager and repeatedly killed working WiFi connections. Every
# production Pi now has a touchscreen, so AP is manual-only via the
# Settings → Connectivity toggle. See ap_control.sh and the new
# health_watchdog service below.
#
# We keep /usr/local/bin/poolaissistant_ap_manager.sh on disk for one
# release so a manual rollback is possible. It will be deleted in the
# next release.
# ============================================
echo "Disabling legacy AP Manager daemon..."
systemctl disable poolaissistant_ap_manager.service 2>/dev/null || true
systemctl stop poolaissistant_ap_manager.service 2>/dev/null || true
# Remove the unit file so it doesn't get re-enabled by daemon-reload
rm -f "$SYSTEMD_DIR/poolaissistant_ap_manager.service"
# Keep the script on disk (per rollback window)
if [ -f "$SCRIPT_DIR/poolaissistant_ap_manager.sh" ]; then
    cp "$SCRIPT_DIR/poolaissistant_ap_manager.sh" "/usr/local/bin/"
    chmod +x "/usr/local/bin/poolaissistant_ap_manager.sh"
fi
mkdir -p /etc/hostapd /etc/dnsmasq.d 2>/dev/null || true

# Install the manual AP control CLI (called by the Flask /settings/ap endpoint
# and the first-boot oneshot).
if [ -f "$SCRIPT_DIR/ap_control.sh" ]; then
    cp "$SCRIPT_DIR/ap_control.sh" "/usr/local/bin/"
    chmod +x "/usr/local/bin/ap_control.sh"
    echo "  -> ap_control.sh installed to /usr/local/bin/"
fi

# Install the health watchdog (reboot if stuck for 10 min)
echo "Installing health watchdog..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant_health_watchdog.service" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant_health_watchdog.service" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/health_watchdog.sh" "/usr/local/bin/"
    chmod +x "/usr/local/bin/health_watchdog.sh"
    mkdir -p /var/lib/poolaissistant 2>/dev/null || true
    systemctl daemon-reload
    systemctl enable poolaissistant_health_watchdog.service
    systemctl restart poolaissistant_health_watchdog.service 2>/dev/null || \
        systemctl start poolaissistant_health_watchdog.service 2>/dev/null || true
    echo "  -> Health watchdog: reboots Pi if network is stuck for >10 min"
else
    echo "  WARNING: Health watchdog service file not found!" >&2
    SKIPPED_COMPONENTS+=("health watchdog")
fi

# Install first-boot AP oneshot (runs once when FIRST_BOOT marker exists)
echo "Installing first-boot AP oneshot..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant-firstboot-ap.service" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant-firstboot-ap.service" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/firstboot_ap.sh" "/usr/local/bin/"
    chmod +x "/usr/local/bin/firstboot_ap.sh"
    systemctl daemon-reload
    systemctl enable poolaissistant-firstboot-ap.service
    echo "  -> First-boot AP: starts setup hotspot if no WiFi/ethernet on fresh clone"
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
    echo "  WARNING: Ports service file not found!" >&2
    SKIPPED_COMPONENTS+=("port configuration")
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

# Install health reporter timer. This drives the heartbeat that updates
# pi_devices.last_seen on the admin server. Without it, the Pi appears
# offline in the admin panel even when it's logging Modbus data normally.
echo "Installing health reporter timer..."
if [ -f "$SCRIPT_DIR/systemd/poolaissistant_health.service" ] && [ -f "$SCRIPT_DIR/systemd/poolaissistant_health.timer" ]; then
    cp "$SCRIPT_DIR/systemd/poolaissistant_health.service" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/systemd/poolaissistant_health.timer" "$SYSTEMD_DIR/"
    mkdir -p /opt/PoolAIssistant/logs 2>/dev/null || true
    systemctl daemon-reload
    systemctl enable poolaissistant_health.timer
    systemctl start poolaissistant_health.timer
    echo "  -> Health reporter: every 15 minutes (heartbeat to admin server)"
else
    echo "  WARNING: Health reporter unit files not found in $SCRIPT_DIR/systemd/" >&2
    SKIPPED_COMPONENTS+=("health reporter timer")
fi

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

# Auto-start the core services so the install is "done done" — previously
# they were only enabled, so SSH-based installers would finish with a Pi
# that wasn't actually serving the UI until the next reboot.
echo "Starting core services..."
systemctl start poolaissistant_ports.service 2>/dev/null || true
systemctl start poolaissistant_ui.service 2>/dev/null || true
# Give the Flask UI a moment to come up, then probe it
sleep 3
if systemctl is-active --quiet poolaissistant_ui.service; then
    echo "  -> poolaissistant_ui: running on http://$(hostname -I | awk '{print $1}'):80/"
else
    echo "  WARNING: poolaissistant_ui failed to start. Check: journalctl -u poolaissistant_ui"
fi

echo
echo "=== Installation Complete ==="
echo

if [ "${#SKIPPED_COMPONENTS[@]}" -gt 0 ]; then
    echo "WARNING: ${#SKIPPED_COMPONENTS[@]} component(s) skipped due to missing files:" >&2
    for c in "${SKIPPED_COMPONENTS[@]}"; do
        echo "  - $c" >&2
    done
    echo >&2
fi

echo "Active timers:"
systemctl list-timers --no-pager | grep -E "(update_check|watchdog|settings_backup|chunk_sync|poolaissistant_health)" || echo "  (none found - check systemctl status)"
echo
echo "To check status:"
echo "  systemctl status update_check.timer"
echo "  systemctl status watchdog.timer"
echo "  systemctl status settings_backup.timer"
echo "  systemctl status poolaissistant_health.timer"
