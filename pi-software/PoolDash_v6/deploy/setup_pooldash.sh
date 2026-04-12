#!/usr/bin/env bash
set -euo pipefail

echo "=== PoolAIssistant Setup Script Starting ==="

# ------------------------------------------------------------
# Safety: handle running as root or normal user
# ------------------------------------------------------------
SUDO_USER="${SUDO_USER:-$USER}"
USER_HOME="/home/$SUDO_USER"
APP_ROOT="$USER_HOME/pooldash"
ZIP_NAME="PoolAIssistant_v5.zip"

echo "Running as user: $SUDO_USER"
echo "App install directory: $APP_ROOT"

# ------------------------------------------------------------
# Install required OS packages
# ------------------------------------------------------------
echo "===> Installing required packages..."
apt update
apt install -y \
    python3 python3-venv python3-pip \
    chromium chromium-common chromium-sandbox \
    unclutter xdotool \
    rsync curl

# ------------------------------------------------------------
# Create application directory
# ------------------------------------------------------------
echo "===> Creating app directory"
mkdir -p "$APP_ROOT"
chown -R "$SUDO_USER:$SUDO_USER" "$APP_ROOT"

# ------------------------------------------------------------
# Populate application directory
# ------------------------------------------------------------
cd "$(dirname "$0")"

if [ -f "$ZIP_NAME" ]; then
    echo "===> Found $ZIP_NAME — extracting"
    sudo -u "$SUDO_USER" unzip -o "$ZIP_NAME" -d "$APP_ROOT"
else
    echo "===> No zip found — copying current directory contents"
    sudo -u "$SUDO_USER" rsync -a --delete ./ "$APP_ROOT/"
fi

# ------------------------------------------------------------
# Fix Windows line endings
# ------------------------------------------------------------
echo "===> Fixing Windows line endings"
find "$APP_ROOT" -type f -name "*.sh" -exec sed -i 's/\r$//' {} \;

# ------------------------------------------------------------
# Make scripts executable
# ------------------------------------------------------------
chmod +x "$APP_ROOT"/*.sh

# ------------------------------------------------------------
# Python virtual environment
# ------------------------------------------------------------
echo "===> Creating Python virtual environment"
cd "$APP_ROOT"
sudo -u "$SUDO_USER" python3 -m venv .venv
sudo -u "$SUDO_USER" .venv/bin/pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    sudo -u "$SUDO_USER" .venv/bin/pip install -r requirements.txt
fi

# ------------------------------------------------------------
# Done
# ------------------------------------------------------------
echo ""
echo "======================================="
echo " PoolAIssistant installation complete"
echo "======================================="
echo ""
echo "To start the system:"
echo "  cd ~/pooldash"
echo "  source .venv/bin/activate"
echo "  python run_ui.py"
echo ""
