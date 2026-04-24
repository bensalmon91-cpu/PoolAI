#!/usr/bin/env bash
#
# ap_control.sh - manual start/stop/status for the PoolAIssistant setup hotspot
# Usage: ap_control.sh {start|stop|status}
#
# This is the synchronous CLI used by the Flask /settings/ap endpoint and
# the first-boot oneshot service. It does NOT run a watchdog loop.
# The background AP auto-failover daemon has been removed in favour of
# explicit user action on the touchscreen.

set -u

# --- Config (overridable via /opt/PoolAIssistant/data/ap_config.sh) -----------
AP_SSID="PoolAI"
AP_PSK=""
AP_OPEN="true"
AP_INTERFACE="wlan0"
AP_IP="192.168.4.1"
AP_SUBNET="255.255.255.0"
AP_DHCP_START="192.168.4.10"
AP_DHCP_END="192.168.4.200"

CONFIG_FILE="/opt/PoolAIssistant/data/ap_config.sh"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
DNSMASQ_CONF="/etc/dnsmasq.d/poolaissistant.conf"
STATE_FILE="/tmp/poolaissistant_ap_state"
LOG_FILE="/opt/PoolAIssistant/data/ap_control.log"
DATA_DIR="/opt/PoolAIssistant/data"

mkdir -p "$DATA_DIR" 2>/dev/null || true
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE" || true

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

# --- Read-only FS handling ---------------------------------------------------
FS_WAS_RO=false
remount_rw() {
    if mount | grep -q "on / type.*ro,"; then
        FS_WAS_RO=true
        mount -o remount,rw / 2>/dev/null || { log "WARNING: remount rw failed"; return 1; }
    fi
    return 0
}
remount_ro() {
    if [[ "$FS_WAS_RO" == "true" ]] && mount | grep -q "on / type.*rw"; then
        mount -o remount,ro / 2>/dev/null || true
        FS_WAS_RO=false
    fi
}

# --- hostapd / dnsmasq config writers ----------------------------------------
escape_hostapd_value() {
    local v="$1"
    v="${v//$'\n'/}"
    v="${v//$'\r'/}"
    echo "$v"
}

write_hostapd_conf() {
    remount_rw || return 1
    mkdir -p /etc/hostapd 2>/dev/null || true

    local safe_ssid safe_psk
    safe_ssid="$(escape_hostapd_value "$AP_SSID")"
    safe_psk="$(escape_hostapd_value "$AP_PSK")"

    if [[ "$AP_OPEN" == "true" ]] || [[ -z "$AP_PSK" ]]; then
        cat > "$HOSTAPD_CONF" <<EOF
interface=$AP_INTERFACE
driver=nl80211
ssid=$safe_ssid
hw_mode=g
channel=6
wmm_enabled=1
auth_algs=1
EOF
    else
        cat > "$HOSTAPD_CONF" <<EOF
interface=$AP_INTERFACE
driver=nl80211
ssid=$safe_ssid
hw_mode=g
channel=6
wmm_enabled=1
auth_algs=1
wpa=2
wpa_passphrase=$safe_psk
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
    fi
    chmod 600 "$HOSTAPD_CONF" 2>/dev/null || true
    remount_ro
    return 0
}

write_dnsmasq_conf() {
    remount_rw || return 1
    mkdir -p /etc/dnsmasq.d 2>/dev/null || true

    # On Raspberry Pi OS the main /etc/dnsmasq.conf ships with conf-dir
    # commented out — without this, our drop-in is ignored and DHCP silently
    # doesn't serve AP clients.
    local main="/etc/dnsmasq.conf"
    if [[ -f "$main" ]] && ! grep -q "^conf-dir=/etc/dnsmasq.d" "$main" 2>/dev/null; then
        if grep -q "^#conf-dir=/etc/dnsmasq.d" "$main" 2>/dev/null; then
            sed -i 's@^#conf-dir=/etc/dnsmasq.d@conf-dir=/etc/dnsmasq.d@' "$main" 2>/dev/null || true
        else
            echo "conf-dir=/etc/dnsmasq.d/,*.conf" >> "$main" 2>/dev/null || true
        fi
    fi

    cat > "$DNSMASQ_CONF" <<EOF
# PoolAIssistant AP DHCP/DNS config
interface=$AP_INTERFACE
bind-interfaces
dhcp-range=$AP_DHCP_START,$AP_DHCP_END,$AP_SUBNET,24h

# We're the DNS server in AP mode — don't forward to upstream
no-resolv

# Resolve the UI's friendly names to the AP IP
address=/poolai.local/$AP_IP
address=/poolaissistant.local/$AP_IP
address=/setup.local/$AP_IP

# Captive-portal hints — phones detect these and auto-open the browser
address=/connectivitycheck.gstatic.com/$AP_IP
address=/www.gstatic.com/$AP_IP
address=/clients3.google.com/$AP_IP
address=/captive.apple.com/$AP_IP
address=/www.apple.com/$AP_IP
address=/detectportal.firefox.com/$AP_IP

domain-needed
bogus-priv

dhcp-option=3,$AP_IP
dhcp-option=6,$AP_IP
EOF
    chmod 644 "$DNSMASQ_CONF" 2>/dev/null || true
    remount_ro
    return 0
}

# --- Lifecycle ---------------------------------------------------------------
verify_ap_running() {
    pgrep -x hostapd >/dev/null 2>&1 || return 1
    systemctl is-active --quiet hostapd 2>/dev/null || return 1
    ip addr show "$AP_INTERFACE" 2>/dev/null | grep -q "$AP_IP" || return 1
    return 0
}

start_ap() {
    log "Starting AP: SSID='$AP_SSID' on $AP_INTERFACE"

    if ! ip link show "$AP_INTERFACE" >/dev/null 2>&1; then
        log "ERROR: interface $AP_INTERFACE missing"
        return 1
    fi

    # Hand wlan0 over from NetworkManager so hostapd can bind to it
    if command -v nmcli >/dev/null 2>&1; then
        nmcli device disconnect "$AP_INTERFACE" 2>/dev/null || true
        nmcli device set "$AP_INTERFACE" managed no 2>/dev/null || true
    fi
    pkill -f "wpa_supplicant.*$AP_INTERFACE" 2>/dev/null || true

    # Assign our static AP address (replaces whatever was on the interface)
    ip link set "$AP_INTERFACE" down 2>/dev/null || true
    sleep 1
    ip addr flush dev "$AP_INTERFACE" 2>/dev/null || true
    ip addr add "$AP_IP/24" dev "$AP_INTERFACE" 2>/dev/null || log "WARN: could not set $AP_IP"
    ip link set "$AP_INTERFACE" up 2>/dev/null || true
    sleep 1

    write_hostapd_conf || { log "ERROR: write hostapd.conf"; return 1; }
    write_dnsmasq_conf || { log "ERROR: write dnsmasq.conf"; return 1; }

    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    sleep 1
    systemctl unmask hostapd 2>/dev/null || true
    systemctl start dnsmasq 2>&1 || log "WARN: dnsmasq start failed"
    systemctl start hostapd 2>&1 || log "WARN: hostapd start failed"
    sleep 3

    if verify_ap_running; then
        echo "ap_running" > "$STATE_FILE" 2>/dev/null || true
        log "SUCCESS: AP up at $AP_IP"
        return 0
    fi
    log "ERROR: AP failed verification after start"
    rm -f "$STATE_FILE" 2>/dev/null || true
    return 1
}

stop_ap() {
    log "Stopping AP"

    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    pkill -x hostapd 2>/dev/null || true
    pkill -f "dnsmasq.*poolaissistant" 2>/dev/null || true

    # The old ap_manager.sh forgot this step — its absence is the reason
    # 192.168.4.1 stuck around on wlan0 after AP handback, which in turn
    # poisoned the /settings device_ip display. Always clear the alias.
    ip addr del "$AP_IP/24" dev "$AP_INTERFACE" 2>/dev/null || true

    # Hand the interface back to NetworkManager so saved WiFi can reconnect
    if command -v nmcli >/dev/null 2>&1; then
        nmcli device set "$AP_INTERFACE" managed yes 2>/dev/null || true
        sleep 1
        nmcli device connect "$AP_INTERFACE" 2>/dev/null || true
    fi

    rm -f "$STATE_FILE" 2>/dev/null || true
    log "AP stopped"
    return 0
}

status_ap() {
    if verify_ap_running; then
        echo "active"
        return 0
    fi
    echo "inactive"
    return 1
}

# --- Dispatch ----------------------------------------------------------------
case "${1:-}" in
    start)  start_ap ;;
    stop)   stop_ap ;;
    status) status_ap ;;
    *)
        echo "Usage: $0 {start|stop|status}" >&2
        exit 2
        ;;
esac
