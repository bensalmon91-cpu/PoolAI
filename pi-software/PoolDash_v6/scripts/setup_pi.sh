#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"
ENV_DIR="/etc/PoolAIssistant"

# Auto-detect network interfaces with fallback
PRIMARY_IF=$(ip route | grep default | awk '{print $5}' | head -n1)
WLAN_IF=$(ip link | grep -o 'wlan[0-9]*' | head -n1)
ETH_IF=$(ip link | grep -o 'eth[0-9]*' | head -n1)

# Use detected interfaces or fall back to standard names
AP_INTERFACE="${WLAN_IF:-wlan0}"
LAN_INTERFACE="${ETH_IF:-eth0}"
LAN_IP="${STATIC_LAN_IP:-192.168.2.1/24}"

# Set to 1 to skip network configuration entirely
SKIP_NETWORK_CONFIG="${SKIP_NETWORK_CONFIG:-0}"

echo "== PoolAIssistant Pi setup =="

sudo mkdir -p "$APP_DIR" "$DATA_DIR" "$ENV_DIR"
sudo chown -R "$USER":"$USER" /opt/PoolAIssistant

echo "Installing system packages..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sqlite3 hostapd dnsmasq

if [ "$SKIP_NETWORK_CONFIG" = "0" ]; then
  echo "Setting static IP for $LAN_INTERFACE..."
  DHCPD_CONF="/etc/dhcpcd.conf"
  BEGIN="# POOLDASH_ETH0_BEGIN"
  END="# POOLDASH_ETH0_END"
  if ! grep -q "$BEGIN" "$DHCPD_CONF"; then
    sudo bash -c "cat >> $DHCPD_CONF" <<EOF

$BEGIN
interface $LAN_INTERFACE
static ip_address=$LAN_IP
$END
EOF
    echo "Configured static IP $LAN_IP on $LAN_INTERFACE"
  else
    echo "Static IP already configured, skipping"
  fi
else
  echo "Skipping network configuration (SKIP_NETWORK_CONFIG=1)"
fi

echo "Copying systemd unit files..."
sudo mkdir -p /etc/systemd/system
sudo cp -f "$APP_DIR/scripts/systemd/poolaissistant_logger.service" /etc/systemd/system/
sudo cp -f "$APP_DIR/scripts/systemd/poolaissistant_ui.service" /etc/systemd/system/
sudo cp -f "$APP_DIR/scripts/systemd/poolaissistant_ap_manager.service" /etc/systemd/system/

echo "Installing AP manager..."
sudo cp -f "$APP_DIR/scripts/poolaissistant_ap_manager.sh" /usr/local/bin/poolaissistant_ap_manager.sh
sudo chmod +x /usr/local/bin/poolaissistant_ap_manager.sh

echo "Creating env file..."
if [ ! -f "$ENV_DIR/poolaissistant.env" ]; then
  sudo cp "$APP_DIR/scripts/poolaissistant.env.example" "$ENV_DIR/poolaissistant.env"
  echo "Created $ENV_DIR/poolaissistant.env (edit POOLS_JSON and paths as needed)."
fi

echo "Disabling Bluetooth..."
sudo systemctl disable --now bluetooth >/dev/null 2>&1 || true
sudo systemctl disable --now hciuart >/dev/null 2>&1 || true

echo "Disabling desktop GUI..."
sudo systemctl set-default multi-user.target
for svc in lightdm gdm3 sddm; do
  if systemctl list-unit-files | grep -q "$svc"; then
    sudo systemctl disable --now "$svc" || true
  fi
done

echo "Enabling PoolAIssistant services..."
sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_logger
sudo systemctl enable poolaissistant_ui
sudo systemctl enable poolaissistant_ap_manager

echo "Setup complete."
echo "Next:"
echo "1) Edit /etc/PoolAIssistant/poolaissistant.env and set POOLS_JSON."
echo "2) Reboot or start services: sudo systemctl start poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager"
