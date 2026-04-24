#!/usr/bin/env bash
set -euo pipefail

# update_wifi.sh <SSID> [PSK]
# Updates NetworkManager (nmcli) or wpa_supplicant as a fallback.
# Run as root (PoolAIssistant calls this via sudo).
# Exit codes: 0=success, 1=connection failed, 2=usage error

SSID="${1:-}"
PSK="${2:-}"
MAX_RETRIES=3
CONNECT_TIMEOUT=20
STABILITY_WAIT=8  # Wait for regulatory domain changes to settle

# Handle read-only filesystem (Pi may be configured with read-only root for SD card protection)
remount_rw() {
  if mount | grep -q "on / type.*ro,"; then
    echo "Remounting root filesystem as read-write..."
    if ! mount -o remount,rw / 2>/dev/null; then
      echo "WARNING: Could not remount filesystem as read-write"
      return 1
    fi
  fi
  return 0
}

remount_ro() {
  if mount | grep -q "on / type.*rw"; then
    echo "Remounting root filesystem as read-only..."
    mount -o remount,ro / 2>/dev/null || true
  fi
}

# Ensure we restore read-only state on exit
trap remount_ro EXIT

if [[ -z "$SSID" ]]; then
  echo "Usage: update_wifi.sh <SSID> [PSK]" >&2
  exit 2
fi

# Validate SSID - reject obviously problematic characters
if [[ "$SSID" == *$'\n'* ]] || [[ "$SSID" == *$'\r'* ]]; then
  echo "ERROR: SSID cannot contain newlines" >&2
  exit 2
fi

# Remount filesystem as read-write for configuration changes
if ! remount_rw; then
  echo "ERROR: Cannot write to filesystem" >&2
  exit 1
fi

# Set regulatory domain to GB to prevent conflicts with APs reporting different regions
# This prevents the "locally_generated disconnect" issue caused by regulatory mismatch
echo "Setting regulatory domain to GB..."
REG_SET=false
# iw is often in /usr/sbin which may not be in PATH
IW_CMD="${IW_CMD:-/usr/sbin/iw}"
if [[ -x "$IW_CMD" ]] && "$IW_CMD" reg set GB 2>/dev/null; then
  REG_SET=true
elif command -v iw >/dev/null 2>&1 && iw reg set GB 2>/dev/null; then
  REG_SET=true
elif echo "GB" > /sys/module/cfg80211/parameters/ieee80211_regdom 2>/dev/null; then
  REG_SET=true
fi

if ! $REG_SET; then
  echo "WARNING: Could not set regulatory domain - connection may be unstable"
fi

# Function to verify actual internet/gateway connectivity
verify_connection() {
  local iface="$1"
  local max_wait=15
  local waited=0

  while [[ $waited -lt $max_wait ]]; do
    # Check if interface has an IP
    local ip
    ip=$(ip -4 addr show "$iface" 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1 || true)

    if [[ -n "$ip" ]]; then
      # Get gateway
      local gw
      gw=$(ip route show dev "$iface" 2>/dev/null | grep "default" | awk '{print $3}' | head -n1 || true)

      if [[ -n "$gw" ]]; then
        # Ping gateway to verify actual connectivity
        if ping -c 1 -W 2 "$gw" >/dev/null 2>&1; then
          echo "Connection verified: IP=$ip, Gateway=$gw"
          return 0
        fi
      fi
    fi

    sleep 1
    ((waited++))
  done

  return 1
}

# Wait for services to actually stop
wait_for_service_stop() {
  local service="$1"
  local max_wait=10
  local waited=0

  systemctl stop "$service" 2>/dev/null || true

  while [[ $waited -lt $max_wait ]]; do
    if ! systemctl is-active --quiet "$service" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
    ((waited++))
  done

  # Force kill if still running
  systemctl kill "$service" 2>/dev/null || true
  sleep 1
}

# Stop AP manager if running (it may be holding wlan0)
echo "Stopping AP services..."
wait_for_service_stop poolaissistant_ap_manager.service
wait_for_service_stop hostapd.service
wait_for_service_stop dnsmasq.service

# Additional wait for processes to fully release interface
for i in {1..10}; do
  if ! pgrep -x "hostapd" >/dev/null 2>&1 && ! pgrep -x "dnsmasq" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# Prefer NetworkManager if present
if command -v nmcli >/dev/null 2>&1; then
  IFACE="wlan0"

  # Ensure WiFi radio is on
  nmcli radio wifi on 2>/dev/null || true

  # Ensure wlan0 is managed by NetworkManager (may be unmanaged due to netplan)
  echo "Setting wlan0 to managed mode..."
  nmcli dev set wlan0 managed yes 2>/dev/null || true
  sleep 1

  # Disconnect current connection first
  nmcli device disconnect "$IFACE" 2>/dev/null || true
  sleep 1

  # Remove ALL existing WiFi profiles for this SSID (including legacy
  # UUID-named duplicates). Iterate every connection and filter by type
  # via the SSID probe: non-wifi profiles return empty from the ssid
  # field, so the comparison fails harmlessly. This replaces the old
  # grep ':wifi$' filter, which never matched because the real type
  # string is '802-11-wireless'.
  while IFS=: read -r conn_name; do
    [[ -z "$conn_name" ]] && continue
    existing_ssid="$(nmcli -t -f 802-11-wireless.ssid con show "$conn_name" 2>/dev/null | cut -d: -f2 || true)"
    if [[ "$existing_ssid" == "$SSID" ]]; then
      echo "Removing existing profile for SSID '$SSID': $conn_name"
      nmcli con delete "$conn_name" 2>/dev/null || true
    fi
  done < <(nmcli -t -f NAME con show)

  # Also delete netplan-generated connections that might conflict
  for conn in $(nmcli -t -f NAME con show | grep "^netplan-wlan0" || true); do
    nmcli con delete "$conn" 2>/dev/null || true
  done

  # Rescan for networks
  echo "Scanning for networks..."
  nmcli device wifi rescan 2>/dev/null || true
  sleep 3

  # Create the connection via nmcli so NetworkManager owns the keyfile
  # format and the UUID. Name = SSID, so subsequent reconfigures can
  # find and replace this exact profile (no more duplicate accretion).
  CONN_NAME="$SSID"
  echo "Creating connection '$CONN_NAME'..."
  if [[ -n "$PSK" ]]; then
    if ! nmcli con add type wifi \
        ifname "$IFACE" \
        con-name "$CONN_NAME" \
        ssid "$SSID" \
        connection.autoconnect yes \
        ipv4.method auto \
        802-11-wireless-security.key-mgmt wpa-psk \
        802-11-wireless-security.psk "$PSK" 2>&1; then
      echo "ERROR: nmcli con add failed"
      exit 1
    fi
  else
    if ! nmcli con add type wifi \
        ifname "$IFACE" \
        con-name "$CONN_NAME" \
        ssid "$SSID" \
        connection.autoconnect yes \
        ipv4.method auto 2>&1; then
      echo "ERROR: nmcli con add failed"
      exit 1
    fi
  fi

  # Try to connect with retries
  connected=false
  for attempt in $(seq 1 $MAX_RETRIES); do
    echo "Connection attempt $attempt of $MAX_RETRIES..."

    if nmcli con up "$CONN_NAME" 2>&1; then
      echo "nmcli con up succeeded"
    else
      echo "nmcli con up failed, retrying..."
      sleep 2
      continue
    fi

    # Wait for regulatory domain changes to settle (can cause disconnect ~4s after connect)
    echo "Waiting for connection to stabilize..."
    sleep $STABILITY_WAIT

    # Verify actual connectivity
    if verify_connection "$IFACE"; then
      # Double-check after brief pause (regulatory domain changes can be delayed)
      sleep 2
      if verify_connection "$IFACE"; then
        connected=true
        break
      fi
    fi

    echo "Connection verification failed, retrying..."
    nmcli device disconnect "$IFACE" 2>/dev/null || true
    sleep 2
  done

  if $connected; then
    IP=$(ip -4 addr show "$IFACE" 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1 || true)
    echo "SUCCESS: Connected to '$SSID'"
    echo "IP address: $IP"

    # Restart AP manager (it will check if WiFi is connected and stay off)
    systemctl start poolaissistant_ap_manager.service 2>/dev/null || true
    exit 0
  else
    echo "FAILED: Could not connect to '$SSID' after $MAX_RETRIES attempts"
    echo "Removing failed profile and restarting AP manager for recovery access..."
    nmcli con delete "$CONN_NAME" 2>/dev/null || true
    systemctl start poolaissistant_ap_manager.service 2>/dev/null || true
    exit 1
  fi
fi

# Fallback: wpa_supplicant (common on Raspberry Pi OS Lite without NM)
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
if [[ -f "$WPA_CONF" ]]; then
  echo "Using wpa_supplicant fallback..."

  # Backup current config
  cp "$WPA_CONF" "${WPA_CONF}.bak"

  # Escape SSID for AWK string matching (not regex)
  # remove existing network blocks for same ssid using string comparison
  tmp="$(mktemp)"
  awk -v target_ssid="$SSID" '
    BEGIN { inblock=0; skip=0; block="" }
    /network=\{/ { inblock=1; block=""; skip=0 }
    {
      if(inblock) { block = block $0 "\n" }
    }
    inblock && /ssid="/ {
      # Extract SSID value using string operations, not regex
      match($0, /ssid="[^"]*"/)
      if (RSTART > 0) {
        ssid_part = substr($0, RSTART+6, RLENGTH-7)
        if (ssid_part == target_ssid) { skip=1 }
      }
    }
    inblock && /\}/ {
      inblock=0
      if(!skip) { printf "%s", block }
      block=""
    }
    !inblock && !/network=\{/ { print }
  ' "$WPA_CONF" > "$tmp" || cp "$WPA_CONF" "$tmp"

  # Ensure file ends with newline
  if [[ -s "$tmp" ]] && [[ "$(tail -c1 "$tmp" | wc -l)" -eq 0 ]]; then
    echo "" >> "$tmp"
  fi

  if [[ -n "$PSK" ]]; then
    # Use wpa_passphrase which handles escaping properly
    if ! wpa_passphrase "$SSID" "$PSK" >> "$tmp" 2>/dev/null; then
      echo "ERROR: wpa_passphrase failed - password may contain special characters"
      rm -f "$tmp"
      exit 1
    fi
  else
    # Open network - escape quotes in SSID
    ESCAPED_SSID_WPA="${SSID//\"/\\\"}"
    cat >> "$tmp" <<EOF

network={
    ssid="${ESCAPED_SSID_WPA}"
    key_mgmt=NONE
}
EOF
  fi

  if ! install -m 600 "$tmp" "$WPA_CONF"; then
    echo "ERROR: Could not write wpa_supplicant config"
    rm -f "$tmp"
    exit 1
  fi
  rm -f "$tmp"

  # restart service
  systemctl restart wpa_supplicant.service || true
  sleep 3

  # Verify connection with wpa_supplicant
  IFACE="wlan0"
  if verify_connection "$IFACE"; then
    echo "SUCCESS: Connected to '$SSID' via wpa_supplicant"
    systemctl start poolaissistant_ap_manager.service 2>/dev/null || true
    exit 0
  else
    echo "FAILED: Could not connect to '$SSID'"
    echo "Restoring previous config and restarting AP..."
    cp "${WPA_CONF}.bak" "$WPA_CONF"
    systemctl restart wpa_supplicant.service || true
    systemctl start poolaissistant_ap_manager.service 2>/dev/null || true
    exit 1
  fi
fi

echo "No supported Wi-Fi manager found (nmcli or wpa_supplicant.conf)." >&2
systemctl start poolaissistant_ap_manager.service 2>/dev/null || true
exit 1
