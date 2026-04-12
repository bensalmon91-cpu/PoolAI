#!/usr/bin/env bash
#
# PoolAIssistant AP Manager - BULLETPROOF VERSION
# Manages Access Point mode for initial setup and recovery
#
# This is a CRITICAL safety service - if network fails, this provides access.
# Design principles:
#   - NEVER exit on errors (no set -e)
#   - Always try to start AP if no network
#   - Verify AP actually started
#   - Retry on failure
#   - Log everything for debugging

# Only fail on unset variables, NOT on command failures
set -u

# Configuration - can be overridden by /opt/PoolAIssistant/data/ap_config.sh
AP_SSID="PoolAI"
AP_PSK=""
AP_OPEN="true"
AP_INTERFACE="wlan0"
AP_IP="192.168.4.1"
AP_SUBNET="255.255.255.0"
AP_DHCP_START="192.168.4.10"
AP_DHCP_END="192.168.4.200"

# Timing configuration
INITIAL_AP_TIME=300          # Keep AP on for 5 minutes minimum on boot
FAST_CHECK_INTERVAL=10       # Check every 10 seconds initially
SLOW_CHECK_INTERVAL=60       # Check every 60 seconds after WiFi stable
WIFI_STABLE_TIME=300         # Consider WiFi stable after 5 minutes connected
AP_RETRY_INTERVAL=30         # Retry AP start every 30 seconds if failed
MAX_AP_RETRIES=10            # Maximum consecutive AP start failures before longer wait
WATCHDOG_TIMEOUT=600         # Reboot if no network AND no AP for 10 minutes (headless recovery)

# Paths
CONFIG_FILE="/opt/PoolAIssistant/data/ap_config.sh"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
DNSMASQ_CONF="/etc/dnsmasq.d/poolaissistant.conf"
STATE_FILE="/tmp/poolaissistant_ap_state"
LOG_FILE="/opt/PoolAIssistant/data/ap_manager.log"
DATA_DIR="/opt/PoolAIssistant/data"

# Track if filesystem was remounted
FS_WAS_RO=false

# Handle read-only filesystem (Pi may be configured with read-only root for SD card protection)
remount_rw() {
  if mount | grep -q "on / type.*ro,"; then
    FS_WAS_RO=true
    if ! mount -o remount,rw / 2>/dev/null; then
      log "WARNING: Could not remount filesystem as read-write"
      return 1
    fi
  fi
  return 0
}

remount_ro() {
  # Only remount if we were the ones who changed it
  if [[ "$FS_WAS_RO" == "true" ]] && mount | grep -q "on / type.*rw"; then
    mount -o remount,ro / 2>/dev/null || true
    FS_WAS_RO=false
  fi
}

# Ensure data directory exists
mkdir -p "$DATA_DIR" 2>/dev/null || true

# Load custom config if exists
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE" || true
fi

# Logging function - logs to file and stdout
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

# Rotate log file if too large (>5MB) - portable version using wc
rotate_log() {
    if [[ -f "$LOG_FILE" ]]; then
        local size
        # Use wc -c for portability (works on both Linux and macOS)
        size=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
        # Remove leading whitespace that wc may add on some systems
        size="${size##* }"
        if [[ "$size" -gt 5242880 ]]; then
            mv "$LOG_FILE" "${LOG_FILE}.old" 2>/dev/null || true
            log "Log rotated"
        fi
    fi
}

# Check if required packages are installed
check_dependencies() {
    local missing=()

    if ! command -v hostapd >/dev/null 2>&1; then
        missing+=("hostapd")
    fi

    if ! command -v dnsmasq >/dev/null 2>&1; then
        missing+=("dnsmasq")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log "WARNING: Missing packages: ${missing[*]}"
        log "Attempting to install missing packages..."
        apt-get update -qq 2>/dev/null || true
        for pkg in "${missing[@]}"; do
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg" 2>/dev/null || {
                log "ERROR: Failed to install $pkg"
            }
        done
    fi

    # Verify after install attempt
    if ! command -v hostapd >/dev/null 2>&1; then
        log "CRITICAL: hostapd not available - AP will not work!"
        return 1
    fi

    return 0
}

# Check if WiFi interface exists
check_interface() {
    if ! ip link show "$AP_INTERFACE" >/dev/null 2>&1; then
        log "ERROR: Interface $AP_INTERFACE does not exist"
        return 1
    fi
    return 0
}

# Validate AP configuration
validate_config() {
    # Validate SSID - no newlines or very long strings
    if [[ "$AP_SSID" == *$'\n'* ]] || [[ "$AP_SSID" == *$'\r'* ]]; then
        log "ERROR: AP_SSID contains invalid characters, using default"
        AP_SSID="PoolAI"
    fi
    if [[ ${#AP_SSID} -gt 32 ]]; then
        log "ERROR: AP_SSID too long (max 32 chars), truncating"
        AP_SSID="${AP_SSID:0:32}"
    fi

    # If open network is enabled, no password validation needed
    if [[ "$AP_OPEN" == "true" ]] || [[ -z "$AP_PSK" ]]; then
        AP_OPEN="true"
        log "AP configured as open network (no password required)"
        return
    fi

    # WPA2 requires minimum 8 character password
    if [[ ${#AP_PSK} -lt 8 ]]; then
        log "ERROR: AP password must be at least 8 characters (WPA2 requirement)."
        log "Using default password instead."
        AP_PSK="12345678"
    fi

    # Validate PSK doesn't contain problematic characters
    if [[ "$AP_PSK" == *$'\n'* ]] || [[ "$AP_PSK" == *$'\r'* ]]; then
        log "ERROR: AP_PSK contains invalid characters, using default"
        AP_PSK="12345678"
    fi
}

# Escape value for hostapd config (basic escaping)
escape_hostapd_value() {
    local val="$1"
    # hostapd uses simple key=value, just ensure no newlines
    val="${val//$'\n'/}"
    val="${val//$'\r'/}"
    echo "$val"
}

write_hostapd_conf() {
    if ! remount_rw; then
        log "ERROR: Cannot write hostapd config - filesystem read-only"
        return 1
    fi

    mkdir -p /etc/hostapd 2>/dev/null || true

    # Escape values for config file
    local SAFE_SSID
    SAFE_SSID="$(escape_hostapd_value "$AP_SSID")"
    local SAFE_PSK
    SAFE_PSK="$(escape_hostapd_value "$AP_PSK")"

    if [[ "$AP_OPEN" == "true" ]] || [[ -z "$AP_PSK" ]]; then
        # Open network (no password)
        cat > "$HOSTAPD_CONF" <<EOF
interface=$AP_INTERFACE
driver=nl80211
ssid=$SAFE_SSID
hw_mode=g
channel=6
wmm_enabled=1
auth_algs=1
EOF
        log "AP configured as OPEN network (no password)"
    else
        # WPA2 protected network
        cat > "$HOSTAPD_CONF" <<EOF
interface=$AP_INTERFACE
driver=nl80211
ssid=$SAFE_SSID
hw_mode=g
channel=6
wmm_enabled=1
auth_algs=1
wpa=2
wpa_passphrase=$SAFE_PSK
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
        log "AP configured with WPA2 password protection"
    fi

    if ! chmod 600 "$HOSTAPD_CONF" 2>/dev/null; then
        log "WARNING: Could not set permissions on hostapd.conf"
    fi

    remount_ro
    return 0
}

write_dnsmasq_conf() {
    if ! remount_rw; then
        log "ERROR: Cannot write dnsmasq config - filesystem read-only"
        return 1
    fi

    mkdir -p /etc/dnsmasq.d 2>/dev/null || true

    # CRITICAL: Ensure main dnsmasq.conf reads our drop-in config
    # On Raspberry Pi OS, conf-dir is commented out by default
    local MAIN_DNSMASQ="/etc/dnsmasq.conf"
    if [[ -f "$MAIN_DNSMASQ" ]]; then
        # Check if conf-dir line exists and is uncommented
        if ! grep -q "^conf-dir=/etc/dnsmasq.d" "$MAIN_DNSMASQ" 2>/dev/null; then
            # Try to uncomment existing line first
            if grep -q "^#conf-dir=/etc/dnsmasq.d" "$MAIN_DNSMASQ" 2>/dev/null; then
                sed -i 's@^#conf-dir=/etc/dnsmasq.d@conf-dir=/etc/dnsmasq.d@' "$MAIN_DNSMASQ" 2>/dev/null || true
                log "Enabled conf-dir in dnsmasq.conf"
            else
                # Add the line if it doesn't exist at all
                echo "conf-dir=/etc/dnsmasq.d/,*.conf" >> "$MAIN_DNSMASQ" 2>/dev/null || true
                log "Added conf-dir to dnsmasq.conf"
            fi
        fi
    fi

    cat > "$DNSMASQ_CONF" <<EOF
# PoolAIssistant AP DHCP/DNS config
interface=$AP_INTERFACE
bind-interfaces
dhcp-range=$AP_DHCP_START,$AP_DHCP_END,$AP_SUBNET,24h

# Prevent dnsmasq from reading /etc/resolv.conf (we're the DNS server in AP mode)
no-resolv

# DNS entries - resolve local names to AP IP
address=/poolai.local/$AP_IP
address=/poolaissistant.local/$AP_IP
address=/setup.local/$AP_IP

# Captive portal style - redirect common domains to AP for setup
# This helps phones detect the "captive portal" and open browser
address=/connectivitycheck.gstatic.com/$AP_IP
address=/www.gstatic.com/$AP_IP
address=/clients3.google.com/$AP_IP
address=/captive.apple.com/$AP_IP
address=/www.apple.com/$AP_IP
address=/detectportal.firefox.com/$AP_IP

domain-needed
bogus-priv

# DHCP options: 3=router/gateway, 6=DNS server
dhcp-option=3,$AP_IP
dhcp-option=6,$AP_IP
EOF

    if ! chmod 644 "$DNSMASQ_CONF" 2>/dev/null; then
        log "WARNING: Could not set permissions on dnsmasq.conf"
    fi

    log "dnsmasq config written to $DNSMASQ_CONF"
    remount_ro
    return 0
}

configure_ap_interface() {
    log "Configuring interface $AP_INTERFACE for AP mode..."

    # Bring interface down first
    ip link set "$AP_INTERFACE" down 2>/dev/null || true
    sleep 1

    # Flush existing addresses
    ip addr flush dev "$AP_INTERFACE" 2>/dev/null || true

    # Set static IP
    ip addr add "$AP_IP/24" dev "$AP_INTERFACE" 2>/dev/null || {
        log "Warning: Could not set IP address (may already be set)"
    }

    # Bring interface up
    ip link set "$AP_INTERFACE" up 2>/dev/null || true
    sleep 1
}

# Verify AP is actually broadcasting
verify_ap_running() {
    # Check if hostapd process is running
    if ! pgrep -x hostapd >/dev/null 2>&1; then
        return 1
    fi

    # Check if hostapd service is active
    if ! systemctl is-active --quiet hostapd 2>/dev/null; then
        return 1
    fi

    # Check if interface has our AP IP
    if ! ip addr show "$AP_INTERFACE" 2>/dev/null | grep -q "$AP_IP"; then
        return 1
    fi

    return 0
}

# Atomically write state file
write_state_file() {
    local state="$1"
    local tmp_file="${STATE_FILE}.tmp.$$"

    if echo "$state" > "$tmp_file" 2>/dev/null; then
        if mv "$tmp_file" "$STATE_FILE" 2>/dev/null; then
            return 0
        fi
        rm -f "$tmp_file" 2>/dev/null || true
    fi

    # Fallback: direct write
    echo "$state" > "$STATE_FILE" 2>/dev/null || true
}

start_ap() {
    log "Starting Access Point: SSID='$AP_SSID' on $AP_INTERFACE"

    # Check interface exists
    if ! check_interface; then
        log "ERROR: Cannot start AP - interface missing"
        return 1
    fi

    # Stop any existing WiFi connection on the interface
    if command -v nmcli >/dev/null 2>&1; then
        nmcli device disconnect "$AP_INTERFACE" 2>/dev/null || true
        # Also tell NetworkManager to not manage this interface temporarily
        nmcli device set "$AP_INTERFACE" managed no 2>/dev/null || true
    fi

    # Stop wpa_supplicant if running on this interface
    pkill -f "wpa_supplicant.*$AP_INTERFACE" 2>/dev/null || true

    # Configure interface
    configure_ap_interface

    # Write configs
    if ! write_hostapd_conf; then
        log "ERROR: Failed to write hostapd config"
        return 1
    fi
    if ! write_dnsmasq_conf; then
        log "ERROR: Failed to write dnsmasq config"
        return 1
    fi

    # Stop services first (clean slate)
    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true
    sleep 1

    # Unmask hostapd (it's often masked by default)
    systemctl unmask hostapd 2>/dev/null || true

    # Start dnsmasq first (DHCP server)
    log "Starting dnsmasq..."
    if ! systemctl start dnsmasq 2>&1; then
        log "Warning: dnsmasq start via systemctl failed, trying direct..."
        dnsmasq -C "$DNSMASQ_CONF" 2>/dev/null || log "Warning: dnsmasq direct start failed"
    fi

    # Start hostapd
    log "Starting hostapd..."
    if ! systemctl start hostapd 2>&1; then
        log "Warning: hostapd start via systemctl failed, trying direct..."
        hostapd -B "$HOSTAPD_CONF" 2>/dev/null || log "Warning: hostapd direct start failed"
    fi

    # Wait for services to stabilize
    sleep 3

    # Verify AP is actually running
    if verify_ap_running; then
        write_state_file "ap_running"
        log "SUCCESS: Access Point started at $AP_IP"
        return 0
    else
        log "ERROR: Access Point failed to start properly"
        rm -f "$STATE_FILE" 2>/dev/null || true
        return 1
    fi
}

stop_ap() {
    if [[ ! -f "$STATE_FILE" ]]; then
        return 0  # Not running
    fi

    log "Stopping Access Point"

    systemctl stop hostapd 2>/dev/null || true
    systemctl stop dnsmasq 2>/dev/null || true

    # Also kill any direct processes
    pkill -x hostapd 2>/dev/null || true
    pkill -f "dnsmasq.*poolaissistant" 2>/dev/null || true

    # Re-enable NetworkManager control if available
    if command -v nmcli >/dev/null 2>&1; then
        nmcli device set "$AP_INTERFACE" managed yes 2>/dev/null || true
        # Trigger auto-connect to any saved WiFi networks
        sleep 1
        nmcli device connect "$AP_INTERFACE" 2>/dev/null || true
    fi

    rm -f "$STATE_FILE" 2>/dev/null || true
    log "Access Point stopped"
}

# Try to connect to any saved WiFi network
try_reconnect_wifi() {
    if ! command -v nmcli >/dev/null 2>&1; then
        return 1
    fi

    # Ensure wlan0 is managed
    nmcli device set "$AP_INTERFACE" managed yes 2>/dev/null || true
    sleep 1

    # Try to connect the device (will use saved connections)
    if nmcli device connect "$AP_INTERFACE" 2>/dev/null; then
        log "Triggered WiFi reconnection"
        sleep 3  # Give it time to connect
        return 0
    fi

    return 1
}

# Get WiFi SSID using multiple methods for compatibility
get_wifi_ssid() {
    local ssid=""

    # Method 1: iwgetid (try multiple paths)
    if command -v iwgetid >/dev/null 2>&1; then
        ssid="$(iwgetid -r 2>/dev/null || true)"
    elif [[ -x /sbin/iwgetid ]]; then
        ssid="$(/sbin/iwgetid -r 2>/dev/null || true)"
    elif [[ -x /usr/sbin/iwgetid ]]; then
        ssid="$(/usr/sbin/iwgetid -r 2>/dev/null || true)"
    fi

    # Method 2: nmcli fallback
    if [[ -z "$ssid" ]] && command -v nmcli >/dev/null 2>&1; then
        ssid="$(nmcli -t -f active,ssid dev wifi 2>/dev/null | grep "^yes:" | cut -d: -f2 | head -1 || true)"
    fi

    # Method 3: iw fallback
    if [[ -z "$ssid" ]] && command -v iw >/dev/null 2>&1; then
        ssid="$(iw dev "$AP_INTERFACE" link 2>/dev/null | grep -i ssid | awk '{print $2}' || true)"
    fi

    echo "$ssid"
}

# Check if connected to a WiFi network (not AP mode)
connected_wifi() {
    local ssid
    ssid="$(get_wifi_ssid)"

    # If no SSID or it's our AP SSID, not connected to external WiFi
    if [[ -z "$ssid" ]] || [[ "$ssid" == "$AP_SSID" ]]; then
        return 1
    fi

    # Verify we have an IP address that is NOT our AP IP
    # wlan0 may have multiple IPs (AP IP + DHCP IP), so check all of them
    local has_non_ap_ip=false
    local ip_addr
    while read -r ip_addr; do
        if [[ -n "$ip_addr" ]] && [[ "$ip_addr" != "$AP_IP" ]]; then
            has_non_ap_ip=true
            break
        fi
    done < <(ip -4 addr show "$AP_INTERFACE" 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)

    if [[ "$has_non_ap_ip" != "true" ]]; then
        return 1
    fi

    # Verify we can reach the gateway (actual connectivity)
    local gw
    gw=$(ip route show dev "$AP_INTERFACE" 2>/dev/null | grep "default" | awk '{print $3}' | head -n1 || true)

    if [[ -z "$gw" ]]; then
        return 1
    fi

    # Quick ping test to gateway (with timeout)
    if ! timeout 3 ping -c 1 -W 2 "$gw" >/dev/null 2>&1; then
        return 1
    fi

    return 0
}

# Check if ethernet is connected and has valid IP
connected_ethernet() {
    local eth_iface="eth0"

    # Check if interface exists
    if ! ip link show "$eth_iface" >/dev/null 2>&1; then
        return 1
    fi

    # Check if interface is up and has carrier
    if ! ip link show "$eth_iface" 2>/dev/null | grep -q "state UP"; then
        return 1
    fi

    # Check for IP address
    if ! ip -4 addr show "$eth_iface" 2>/dev/null | grep -q "inet "; then
        return 1
    fi

    # Verify gateway reachable (with timeout)
    local gw
    gw=$(ip route show dev "$eth_iface" 2>/dev/null | grep "default" | awk '{print $3}' | head -n1 || true)

    if [[ -n "$gw" ]]; then
        if timeout 3 ping -c 1 -W 2 "$gw" >/dev/null 2>&1; then
            return 0
        fi
    fi

    # Even without gateway ping, if we have an IP that's good enough
    return 0
}

# Check if we have ANY network connectivity
has_network() {
    if connected_wifi; then
        return 0
    fi
    if connected_ethernet; then
        return 0
    fi
    return 1
}

# Main loop
main() {
    log "=========================================="
    log "PoolAIssistant AP Manager starting"
    log "=========================================="
    log "Configuration:"
    log "  SSID: $AP_SSID"
    log "  Interface: $AP_INTERFACE"
    log "  IP: $AP_IP"
    log "  Initial AP time: ${INITIAL_AP_TIME}s"

    # Wait for network interfaces to initialize at boot
    # This is critical - without this delay, interfaces may not be ready
    log "Waiting 5 seconds for network interfaces to initialize..."
    sleep 5

    # Rotate log if needed
    rotate_log

    # Validate configuration
    validate_config

    # Check dependencies (but don't fail if missing - try anyway)
    check_dependencies || log "Warning: Dependency check had issues"

    # Check interface
    if ! check_interface; then
        log "ERROR: WiFi interface not found. Waiting for it to appear..."
        while ! check_interface; do
            sleep 10
        done
        log "Interface $AP_INTERFACE is now available"
    fi

    # Check if WiFi is already connected (e.g., NetworkManager auto-connected to saved network)
    # Give NetworkManager a bit more time to auto-connect before deciding
    log "Checking for existing WiFi connection..."

    local ap_start_failures=0

    # First check if already connected
    if connected_wifi; then
        log "WiFi already connected - skipping AP startup"
        log "AP will start automatically if WiFi connection is lost"
    else
        # Not connected yet - try to trigger reconnection to saved networks
        log "WiFi not connected, attempting to reconnect to saved networks..."
        try_reconnect_wifi
        sleep 5  # Give NetworkManager time to establish connection

        # Check again after reconnect attempt
        if connected_wifi; then
            log "WiFi reconnected successfully - skipping AP startup"
            log "AP will start automatically if WiFi connection is lost"
        else
            # Still no WiFi connection - start AP for initial access (safety feature)
            log "No WiFi connection available - starting AP for access..."

            if ! start_ap; then
                log "Initial AP start failed, will retry..."
                ap_start_failures=1
            fi
        fi
    fi

    local boot_time
    boot_time=$(date +%s)
    local wifi_connected_since=0
    local check_interval=$FAST_CHECK_INTERVAL
    local last_network_check=0
    local last_accessible=$boot_time  # Track when we were last accessible (network OR working AP)

    while true; do
        local now
        now=$(date +%s)
        local time_since_boot=$((now - boot_time))

        # WATCHDOG: Check if we've been inaccessible for too long (headless recovery)
        local inaccessible_time=$((now - last_accessible))
        if [[ $inaccessible_time -gt $WATCHDOG_TIMEOUT ]] && [[ $time_since_boot -gt $WATCHDOG_TIMEOUT ]]; then
            log "WATCHDOG: No network AND no working AP for ${inaccessible_time}s - REBOOTING for recovery"
            sync
            sleep 2
            reboot
            exit 1  # Should not reach here
        fi

        # Check connectivity
        # Note: We track ethernet separately from WiFi
        # AP should only stop when WiFi is connected (users need AP to configure WiFi)
        # Ethernet alone should NOT stop the AP
        local has_wifi=false
        local has_eth=false
        connected_wifi && has_wifi=true
        connected_ethernet && has_eth=true

        if [[ "$has_eth" == "true" ]]; then
            last_accessible=$now  # Ethernet gives us accessibility
        fi

        if [[ "$has_wifi" == "true" ]]; then
            last_accessible=$now  # WiFi also gives us accessibility
            # WiFi is connected
            if [[ $wifi_connected_since -eq 0 ]]; then
                wifi_connected_since=$now
                log "WiFi connected"
            fi

            local connected_duration=$((now - wifi_connected_since))

            # If WiFi has been stable AND we're past initial period, stop AP
            if [[ $time_since_boot -gt $INITIAL_AP_TIME ]] && [[ $connected_duration -gt 60 ]]; then
                if [[ -f "$STATE_FILE" ]]; then
                    log "WiFi stable for ${connected_duration}s, stopping AP to free WiFi radio"
                    stop_ap
                fi

                # Slow down checking once WiFi is stable
                if [[ $connected_duration -gt $WIFI_STABLE_TIME ]]; then
                    check_interval=$SLOW_CHECK_INTERVAL
                fi
            fi

            ap_start_failures=0  # Reset failure counter

        else
            # No network - MUST have AP running
            wifi_connected_since=0
            check_interval=$FAST_CHECK_INTERVAL

            # Check if AP is supposed to be running but isn't
            if [[ -f "$STATE_FILE" ]] && ! verify_ap_running; then
                log "AP state file exists but AP not running - restarting..."
                rm -f "$STATE_FILE"
            fi

            # Start AP if not running
            # If AP is running and verified, we're accessible via AP
            if [[ -f "$STATE_FILE" ]] && verify_ap_running; then
                last_accessible=$now  # AP is working, we're accessible
            fi

            if [[ ! -f "$STATE_FILE" ]]; then
                log "No network detected, ensuring AP is running..."
                if start_ap; then
                    ap_start_failures=0
                    last_accessible=$now  # AP just started successfully
                else
                    ((ap_start_failures++)) || true
                    log "AP start failed (attempt $ap_start_failures)"

                    # If many failures, wait longer before retrying
                    if [[ $ap_start_failures -ge $MAX_AP_RETRIES ]]; then
                        log "Too many AP failures, waiting 60s before retry..."
                        sleep 60
                        ap_start_failures=0  # Reset and try again
                    else
                        sleep "$AP_RETRY_INTERVAL"
                    fi
                    continue
                fi
            fi
        fi

        sleep "$check_interval"
    done
}

# Handle signals gracefully
cleanup() {
    log "Shutting down AP manager (signal received)"
    stop_ap
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

# Run main
main
