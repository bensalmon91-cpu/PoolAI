#!/usr/bin/env bash
set -euo pipefail

# update_ethernet.sh <MODE> [IP] [NETMASK] [GATEWAY]
# MODE: "dhcp" or "static"
# Run as root (PoolAIssistant calls this via sudo).

MODE="${1:-dhcp}"
IP="${2:-}"
NETMASK="${3:-24}"
GATEWAY="${4:-}"

IFACE="eth0"

# Validate mode
if [[ "$MODE" != "dhcp" && "$MODE" != "static" ]]; then
  echo "Usage: update_ethernet.sh <dhcp|static> [IP] [NETMASK] [GATEWAY]" >&2
  exit 2
fi

# For static mode, require IP
if [[ "$MODE" == "static" && -z "$IP" ]]; then
  echo "Static mode requires IP address" >&2
  exit 2
fi

echo "Configuring $IFACE in $MODE mode..."

# Check if using NetworkManager
if command -v nmcli >/dev/null 2>&1; then
  # Find the ethernet connection name
  CONN=$(nmcli -t -f NAME,DEVICE con show --active | grep ":$IFACE$" | cut -d: -f1 || true)

  if [[ -z "$CONN" ]]; then
    # Try to find any ethernet connection
    CONN=$(nmcli -t -f NAME,TYPE con show | grep ":ethernet$" | head -n1 | cut -d: -f1 || true)
  fi

  if [[ -z "$CONN" ]]; then
    # Create a new connection
    CONN="Wired-$IFACE"
    nmcli con add type ethernet con-name "$CONN" ifname "$IFACE" 2>/dev/null || true
  fi

  if [[ "$MODE" == "dhcp" ]]; then
    echo "Setting $IFACE to DHCP..."
    nmcli con modify "$CONN" ipv4.method auto
    nmcli con modify "$CONN" ipv4.addresses ""
    nmcli con modify "$CONN" ipv4.gateway ""
  else
    echo "Setting $IFACE to static IP: $IP/$NETMASK"
    nmcli con modify "$CONN" ipv4.method manual
    nmcli con modify "$CONN" ipv4.addresses "$IP/$NETMASK"
    if [[ -n "$GATEWAY" ]]; then
      nmcli con modify "$CONN" ipv4.gateway "$GATEWAY"
      echo "Gateway: $GATEWAY"
    else
      nmcli con modify "$CONN" ipv4.gateway ""
    fi
  fi

  # Apply changes
  nmcli con down "$CONN" 2>/dev/null || true
  sleep 1
  nmcli con up "$CONN" 2>/dev/null || true

  echo "Ethernet configuration applied."
  exit 0
fi

# Fallback: dhcpcd.conf (Raspberry Pi OS without NetworkManager)
DHCPCD_CONF="/etc/dhcpcd.conf"
if [[ -f "$DHCPCD_CONF" ]]; then
  # Remove existing eth0 static configuration
  BEGIN="# POOLAISSISTANT_ETH0_BEGIN"
  END="# POOLAISSISTANT_ETH0_END"

  # Create temp file without our block
  tmp=$(mktemp)
  awk -v begin="$BEGIN" -v end="$END" '
    $0 == begin { skip=1; next }
    $0 == end { skip=0; next }
    !skip { print }
  ' "$DHCPCD_CONF" > "$tmp"

  if [[ "$MODE" == "static" ]]; then
    # Add our static configuration
    cat >> "$tmp" <<EOF

$BEGIN
interface $IFACE
static ip_address=$IP/$NETMASK
EOF
    if [[ -n "$GATEWAY" ]]; then
      echo "static routers=$GATEWAY" >> "$tmp"
    fi
    echo "$END" >> "$tmp"
  fi

  # Apply the configuration
  install -m 644 "$tmp" "$DHCPCD_CONF"
  rm -f "$tmp"

  # Restart dhcpcd
  systemctl restart dhcpcd.service 2>/dev/null || true

  echo "Ethernet configuration applied via dhcpcd."
  exit 0
fi

# Fallback: netplan (Ubuntu/newer systems)
NETPLAN_DIR="/etc/netplan"
if [[ -d "$NETPLAN_DIR" ]]; then
  NETPLAN_FILE="$NETPLAN_DIR/99-poolaissistant-eth0.yaml"

  if [[ "$MODE" == "dhcp" ]]; then
    # Remove our custom config, let default handle it
    rm -f "$NETPLAN_FILE"
  else
    cat > "$NETPLAN_FILE" <<EOF
network:
  version: 2
  ethernets:
    $IFACE:
      addresses:
        - $IP/$NETMASK
EOF
    if [[ -n "$GATEWAY" ]]; then
      cat >> "$NETPLAN_FILE" <<EOF
      routes:
        - to: default
          via: $GATEWAY
EOF
    fi
  fi

  netplan apply 2>/dev/null || true
  echo "Ethernet configuration applied via netplan."
  exit 0
fi

echo "No supported network manager found (nmcli, dhcpcd, or netplan)." >&2
exit 1
