#!/usr/bin/env bash
set -euo pipefail

# network_reset.sh
# Emergency network reset script
# Resets all network settings to defaults and forces AP mode
# Can be called from web UI, button handler, or command line

echo "========================================"
echo "PoolAIssistant Network Reset"
echo "========================================"

# Stop services that might interfere
echo "Stopping network services..."
systemctl stop poolaissistant_ap_manager.service 2>/dev/null || true
systemctl stop hostapd.service 2>/dev/null || true
systemctl stop dnsmasq.service 2>/dev/null || true

# Reset WiFi
echo "Resetting WiFi configuration..."
if command -v nmcli >/dev/null 2>&1; then
    # Disconnect
    nmcli device disconnect wlan0 2>/dev/null || true

    # Delete all WiFi connections
    for conn in $(nmcli -t -f NAME,TYPE con show | grep ":wifi$" | cut -d: -f1); do
        echo "Removing WiFi: $conn"
        nmcli con delete "$conn" 2>/dev/null || true
    done

    # Delete netplan connections
    for conn in $(nmcli -t -f NAME con show | grep "^netplan-wlan" 2>/dev/null || true); do
        nmcli con delete "$conn" 2>/dev/null || true
    done
fi

# Clear wpa_supplicant if present
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
if [[ -f "$WPA_CONF" ]]; then
    echo "Clearing wpa_supplicant config..."
    cat > "$WPA_CONF" <<'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB
EOF
    chmod 600 "$WPA_CONF"
fi

# Reset Ethernet to DHCP
echo "Resetting Ethernet to DHCP..."
if command -v nmcli >/dev/null 2>&1; then
    # Find ethernet connection
    ETH_CONN=$(nmcli -t -f NAME,TYPE con show | grep ":ethernet$" | head -n1 | cut -d: -f1 || true)
    if [[ -n "$ETH_CONN" ]]; then
        nmcli con mod "$ETH_CONN" ipv4.method auto 2>/dev/null || true
        nmcli con mod "$ETH_CONN" ipv4.addresses "" 2>/dev/null || true
        nmcli con mod "$ETH_CONN" ipv4.gateway "" 2>/dev/null || true
        nmcli con up "$ETH_CONN" 2>/dev/null || true
    fi
fi

# Also check dhcpcd.conf
DHCPCD_CONF="/etc/dhcpcd.conf"
if [[ -f "$DHCPCD_CONF" ]]; then
    echo "Removing static config from dhcpcd.conf..."
    # Remove our custom blocks
    BEGIN="# POOLAISSISTANT_ETH0_BEGIN"
    END="# POOLAISSISTANT_ETH0_END"
    tmp=$(mktemp)
    awk -v begin="$BEGIN" -v end="$END" '
        $0 == begin { skip=1; next }
        $0 == end { skip=0; next }
        !skip { print }
    ' "$DHCPCD_CONF" > "$tmp"
    install -m 644 "$tmp" "$DHCPCD_CONF"
    rm -f "$tmp"
fi

# Remove netplan custom config
NETPLAN_FILE="/etc/netplan/99-poolaissistant-eth0.yaml"
if [[ -f "$NETPLAN_FILE" ]]; then
    echo "Removing custom netplan config..."
    rm -f "$NETPLAN_FILE"
    netplan apply 2>/dev/null || true
fi

# Clear AP config overrides
AP_CONFIG="/opt/PoolAIssistant/data/ap_config.sh"
if [[ -f "$AP_CONFIG" ]]; then
    echo "Removing AP config overrides..."
    rm -f "$AP_CONFIG"
fi

# Force AP to start
echo "Starting Access Point..."
systemctl start poolaissistant_ap_manager.service

# Wait for AP to come up
sleep 5

# Show result
echo ""
echo "========================================"
echo "Network Reset Complete"
echo "========================================"
echo ""
echo "WiFi connections: Cleared"
echo "Ethernet: Reset to DHCP"
echo "Access Point: Starting"
echo ""
echo "Connect to WiFi network 'PoolAI' (open network, no password)"
echo "Then browse to http://192.168.4.1 to configure"
echo ""
