#!/usr/bin/env bash
#
# update_wifi_ip.sh <MODE> [IP] [NETMASK] [GATEWAY] [DNS]
#   MODE:    "dhcp" or "static"
#   IP:      e.g. 10.0.30.50    (no CIDR — netmask is separate)
#   NETMASK: e.g. 24            (CIDR suffix)
#   GATEWAY: e.g. 10.0.30.1     (required for static)
#   DNS:     optional comma-separated list, e.g. 8.8.8.8,1.1.1.1
#
# Modifies the currently-active WiFi connection on wlan0 to use the given
# IP configuration. Called via sudo from the Flask web UI's
# /settings/wifi/ip endpoint.
#
# WARNING: misconfigured static settings can leave the Pi unreachable.
# The UI warns the user; recovery requires touchscreen or console access.

set -euo pipefail

MODE="${1:-dhcp}"
IP="${2:-}"
NETMASK="${3:-24}"
GATEWAY="${4:-}"
DNS="${5:-}"

IFACE="wlan0"

if [[ "$MODE" != "dhcp" && "$MODE" != "static" ]]; then
    echo "Usage: update_wifi_ip.sh <dhcp|static> [IP] [NETMASK] [GATEWAY] [DNS]" >&2
    exit 2
fi

if [[ "$MODE" == "static" ]]; then
    if [[ -z "$IP" ]]; then
        echo "ERROR: static mode requires IP" >&2
        exit 2
    fi
    if [[ -z "$GATEWAY" ]]; then
        echo "ERROR: static mode requires GATEWAY" >&2
        exit 2
    fi
fi

if ! command -v nmcli >/dev/null 2>&1; then
    echo "ERROR: nmcli not available — WiFi IP config requires NetworkManager" >&2
    exit 1
fi

# Find the active WiFi profile bound to wlan0. WiFi IP is a property of the
# connection profile, not the interface, so we must target the right one.
CONN="$(nmcli -t -f NAME,TYPE,DEVICE con show --active \
        | awk -F: -v i="$IFACE" '$2=="802-11-wireless" && $3==i {print $1; exit}')"

if [[ -z "$CONN" ]]; then
    echo "ERROR: no active WiFi profile on $IFACE — connect to a network first" >&2
    exit 1
fi

echo "Active WiFi profile: $CONN"

# Handle read-only root filesystems. NetworkManager writes keyfiles to
# /etc/NetworkManager/system-connections/ — the FS must be writable.
FS_WAS_RO=false
remount_rw() {
    if mount | grep -q "on / type.*ro,"; then
        FS_WAS_RO=true
        mount -o remount,rw / 2>/dev/null || {
            echo "ERROR: could not remount filesystem read-write" >&2
            return 1
        }
    fi
}
remount_ro() {
    if [[ "$FS_WAS_RO" == "true" ]]; then
        mount -o remount,ro / 2>/dev/null || true
    fi
}
trap remount_ro EXIT

remount_rw

if [[ "$MODE" == "dhcp" ]]; then
    echo "Setting $CONN to DHCP..."
    nmcli con modify "$CONN" \
        ipv4.method auto \
        ipv4.addresses "" \
        ipv4.gateway "" \
        ipv4.dns ""
else
    # No DNS supplied? Fall back to the gateway. With ipv4.method=manual,
    # leaving ipv4.dns="" means NM does NOT use DHCP-discovered DNS — the
    # Pi loses name resolution entirely (cloud admin reporting, updates).
    # Most home/office gateways act as DNS forwarders, so the gateway is
    # the safest blind default.
    EFFECTIVE_DNS="${DNS:-$GATEWAY}"
    echo "Setting $CONN to static $IP/$NETMASK gw=$GATEWAY dns=$EFFECTIVE_DNS"
    nmcli con modify "$CONN" \
        ipv4.method manual \
        ipv4.addresses "$IP/$NETMASK" \
        ipv4.gateway "$GATEWAY" \
        ipv4.dns "$EFFECTIVE_DNS"
fi

# Apply: reactivate the connection so the new IP takes effect immediately.
# This will briefly drop wlan0 — callers that need to report back to the
# user should take care (the UI just shows a flash message).
echo "Reactivating $CONN..."
nmcli con down "$CONN" 2>/dev/null || true
sleep 1
if ! nmcli con up "$CONN" 2>&1; then
    echo "WARNING: nmcli con up failed. The profile is saved; next reboot will retry."
    exit 1
fi

# Report the new IP so the caller (Flask UI) can show it back to the user.
sleep 2
NEW_IP=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="inet") {print $(i+1); exit}}')
echo "SUCCESS: $IFACE now at $NEW_IP"
