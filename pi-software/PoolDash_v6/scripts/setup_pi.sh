#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"
ENV_DIR="/etc/PoolAIssistant"
POOLAI_USER="${POOLAI_USER:-poolai}"

# Pool-subnet IP for eth0. Default matches the original production unit
# convention (.100). Override per Pi when deploying multiple devices on
# the same pool LAN — e.g. POOLAI_ETH_IP=192.168.200.101/24
POOLAI_ETH_IP="${POOLAI_ETH_IP:-192.168.200.100/24}"

# Default behaviour: configure eth0 with a static IP on the pool subnet.
# Set to 1 to skip if this Pi's eth0 is managed by something else.
SKIP_NETWORK_CONFIG="${SKIP_NETWORK_CONFIG:-0}"

echo "== PoolAIssistant Pi setup =="

# --- Service account ---------------------------------------------------------
# All systemd units run as $POOLAI_USER, so it must exist before we install
# them. Idempotent: skip if the user is already present.
if ! id "$POOLAI_USER" >/dev/null 2>&1; then
    echo "Creating service user: $POOLAI_USER"
    sudo useradd -m -s /bin/bash -G sudo,dialout,gpio,i2c,spi "$POOLAI_USER"
    echo "$POOLAI_USER:12345678" | sudo chpasswd
    sudo loginctl enable-linger "$POOLAI_USER"
fi

# --- Directories -------------------------------------------------------------
# Always chown to the service user (was previously $USER, which gave wrong
# ownership when the installer was run via sudo from a different account).
sudo mkdir -p "$APP_DIR" "$DATA_DIR" "$ENV_DIR"
sudo chown -R "$POOLAI_USER:$POOLAI_USER" /opt/PoolAIssistant

# --- /etc/hosts hostname entry ----------------------------------------------
# sudo emits "unable to resolve host …" warnings on every invocation if
# the current hostname isn't in /etc/hosts. Cosmetic but noisy.
THIS_HOST="$(hostname)"
if ! grep -qE "^127\.0\.1\.1[[:space:]]+${THIS_HOST}\b" /etc/hosts; then
    echo "127.0.1.1 ${THIS_HOST}" | sudo tee -a /etc/hosts >/dev/null
fi

echo "Installing system packages..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-venv python3-pip sqlite3 hostapd dnsmasq

# --- Python venv -------------------------------------------------------------
# Without this, poolaissistant_ui.service crashes on first start because
# its ExecStart path /opt/PoolAIssistant/venv/bin/python doesn't exist.
if [ ! -x "/opt/PoolAIssistant/venv/bin/python" ]; then
    echo "Creating Python venv at /opt/PoolAIssistant/venv..."
    sudo -u "$POOLAI_USER" python3 -m venv /opt/PoolAIssistant/venv
    sudo -u "$POOLAI_USER" /opt/PoolAIssistant/venv/bin/pip install --quiet --upgrade pip
fi
if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "Installing Python requirements..."
    sudo -u "$POOLAI_USER" /opt/PoolAIssistant/venv/bin/pip install --quiet -r "$APP_DIR/requirements.txt"
fi

# --- eth0 network config (NetworkManager) -----------------------------------
# The previous version wrote a static IP into /etc/dhcpcd.conf — but the Pi
# uses NetworkManager, so it had no effect AND its default 192.168.2.1/24
# was wrong (pool subnet is 192.168.200.x). Now: create a real NM profile.
# Only creates the profile when none exists, so re-runs leave any custom
# config alone.
if [ "$SKIP_NETWORK_CONFIG" = "0" ] && command -v nmcli >/dev/null 2>&1; then
    echo "Configuring eth0 (PoolAI-Ethernet, $POOLAI_ETH_IP, no default route)..."
    # Remove broken auto-generated profiles that get stuck waiting for DHCP
    # on the static-only pool subnet.
    for stale in $(nmcli -t -f NAME con show 2>/dev/null | grep -E '^netplan-eth0$' || true); do
        sudo nmcli con delete "$stale" 2>/dev/null || true
    done
    if ! nmcli -t -f NAME con show 2>/dev/null | grep -Fxq 'PoolAI-Ethernet'; then
        sudo nmcli con add type ethernet ifname eth0 con-name 'PoolAI-Ethernet' \
            ipv4.method manual \
            ipv4.addresses "$POOLAI_ETH_IP" \
            ipv4.never-default yes \
            ipv6.method auto \
            connection.autoconnect yes \
            >/dev/null
        sudo nmcli con up 'PoolAI-Ethernet' 2>/dev/null || \
            echo "  WARNING: PoolAI-Ethernet created but failed to activate (eth0 cable in?)"
    else
        echo "  PoolAI-Ethernet profile already exists, leaving as-is"
    fi
else
    echo "Skipping eth0 network configuration (SKIP_NETWORK_CONFIG=$SKIP_NETWORK_CONFIG)"
fi

echo "Copying core systemd unit files..."
sudo mkdir -p /etc/systemd/system
sudo cp -f "$APP_DIR/scripts/systemd/poolaissistant_logger.service" /etc/systemd/system/
sudo cp -f "$APP_DIR/scripts/systemd/poolaissistant_ui.service" /etc/systemd/system/

echo "Creating env file..."
if [ ! -f "$ENV_DIR/poolaissistant.env" ]; then
    sudo cp "$APP_DIR/scripts/poolaissistant.env.example" "$ENV_DIR/poolaissistant.env"
    echo "Created $ENV_DIR/poolaissistant.env"
fi

echo "Disabling Bluetooth..."
sudo systemctl disable --now bluetooth >/dev/null 2>&1 || true
sudo systemctl disable --now hciuart >/dev/null 2>&1 || true

echo "Disabling desktop GUI..."
sudo systemctl set-default multi-user.target >/dev/null
for svc in lightdm gdm3 sddm; do
    if systemctl list-unit-files | grep -q "$svc"; then
        sudo systemctl disable --now "$svc" || true
    fi
done

echo "Enabling PoolAIssistant core services..."
sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_logger
sudo systemctl enable poolaissistant_ui

echo "Setup complete."
echo
echo "Next:"
echo "  1) sudo bash $APP_DIR/scripts/install_services.sh   (timers + extras)"
echo "  2) sudo bash $APP_DIR/scripts/ensure_dependencies.sh   (sudoers + symlinks)"
echo "  3) Configure pool controllers via the web UI (Settings -> Controllers)"
