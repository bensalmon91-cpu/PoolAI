#!/usr/bin/env bash
# PoolAIssistant Kiosk Setup Script
# Copyright Ben Salmon 2026. All Rights Reserved.
#
# This script configures a Raspberry Pi for kiosk mode:
# - Enables SSH for remote access
# - Enables PoolAIssistant services
# - Disables desktop environment
# - Configures touchscreen scrolling
# - Locks down unneeded services
# - Sets up Chromium kiosk mode (optional)
#
# Usage: sudo ./kiosk_setup.sh [--with-browser]

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo)"
    exit 1
fi

# Parse arguments
WITH_BROWSER=false
for arg in "$@"; do
    case $arg in
        --with-browser)
            WITH_BROWSER=true
            shift
            ;;
    esac
done

echo "========================================"
echo " PoolAIssistant Kiosk Setup"
echo "========================================"
echo

# ============================================
# 1. ENABLE SSH
# ============================================
log_info "Enabling SSH..."
systemctl enable ssh
systemctl start ssh
log_info "SSH enabled and started"

# ============================================
# 2. ENABLE POOLAISSISTANT SERVICES
# ============================================
log_info "Enabling PoolAIssistant services..."

SERVICES=(
    "poolaissistant_ui"
    "poolaissistant_logger"
    "poolaissistant_ap_manager"
)

for svc in "${SERVICES[@]}"; do
    if systemctl list-unit-files | grep -q "$svc"; then
        systemctl enable "$svc" 2>/dev/null || true
        log_info "  Enabled: $svc"
    else
        log_warn "  Not found: $svc (install services first)"
    fi
done

# ============================================
# 3. DISABLE DESKTOP ENVIRONMENT
# ============================================
log_info "Disabling desktop environment..."

# Set CLI boot as default
systemctl set-default multi-user.target

# Disable display managers
for dm in lightdm gdm3 sddm xdm lxdm; do
    if systemctl list-unit-files | grep -q "^$dm"; then
        systemctl disable --now "$dm" 2>/dev/null || true
        log_info "  Disabled: $dm"
    fi
done

# ============================================
# 4. DISABLE BLUETOOTH
# ============================================
log_info "Disabling Bluetooth..."
systemctl disable --now bluetooth 2>/dev/null || true
systemctl disable --now hciuart 2>/dev/null || true

# Add to config.txt if not already present
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

if [ -f "$CONFIG_FILE" ]; then
    if ! grep -q "dtoverlay=disable-bt" "$CONFIG_FILE"; then
        echo "" >> "$CONFIG_FILE"
        echo "# Disable Bluetooth" >> "$CONFIG_FILE"
        echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
        log_info "  Added dtoverlay=disable-bt to config.txt"
    fi
fi

# ============================================
# 5. CONFIGURE TOUCHSCREEN SCROLLING
# ============================================
log_info "Configuring touchscreen scrolling..."

# Create libinput config for natural scrolling and touch support
LIBINPUT_CONF="/etc/X11/xorg.conf.d/40-libinput.conf"
mkdir -p "$(dirname "$LIBINPUT_CONF")"

cat > "$LIBINPUT_CONF" << 'EOF'
# PoolAIssistant touchscreen configuration
# Enables natural scrolling and touch gestures

Section "InputClass"
    Identifier "libinput touchscreen catchall"
    MatchIsTouchscreen "on"
    MatchDevicePath "/dev/input/event*"
    Driver "libinput"
    Option "Tapping" "on"
    Option "TappingDrag" "on"
    Option "NaturalScrolling" "true"
    Option "ScrollMethod" "twofinger"
EndSection

Section "InputClass"
    Identifier "libinput touchpad catchall"
    MatchIsTouchpad "on"
    MatchDevicePath "/dev/input/event*"
    Driver "libinput"
    Option "Tapping" "on"
    Option "NaturalScrolling" "true"
    Option "ScrollMethod" "twofinger"
EndSection
EOF
log_info "  Created libinput touchscreen config"

# Create udev rule for touchscreen permissions
UDEV_RULE="/etc/udev/rules.d/99-touchscreen.rules"
cat > "$UDEV_RULE" << 'EOF'
# Allow input group access to touchscreen
SUBSYSTEM=="input", GROUP="input", MODE="0660"
KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="*touch*", GROUP="input", MODE="0660"
KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="*Touch*", GROUP="input", MODE="0660"
EOF
log_info "  Created udev rules for touchscreen"

# Reload udev rules
udevadm control --reload-rules
udevadm trigger

# ============================================
# 6. LOCK DOWN UNNEEDED SERVICES
# ============================================
log_info "Disabling unneeded services..."

DISABLE_SERVICES=(
    # "avahi-daemon"         # mDNS/Bonjour - KEEP ENABLED for poolaissistant.local access
    "ModemManager"           # Modem support
    "wpa_supplicant"         # Managed by NetworkManager if used
    "triggerhappy"           # Hotkey daemon
    "raspi-config"           # Config utility
    "rpi-eeprom-update"      # EEPROM updates (can run manually)
)

for svc in "${DISABLE_SERVICES[@]}"; do
    if systemctl list-unit-files | grep -q "^$svc"; then
        systemctl disable "$svc" 2>/dev/null || true
        systemctl stop "$svc" 2>/dev/null || true
        log_info "  Disabled: $svc"
    fi
done

# Keep essential services
log_info "Keeping essential services enabled:"
log_info "  - systemd-timesyncd (NTP time sync)"
log_info "  - NetworkManager or dhcpcd (networking)"
log_info "  - ssh (remote access)"

# ============================================
# 7. CONFIGURE BROWSER KIOSK (OPTIONAL)
# ============================================
if [ "$WITH_BROWSER" = true ]; then
    log_info "Setting up Chromium kiosk mode..."

    # Install chromium if not present
    if ! command -v chromium-browser &> /dev/null; then
        apt-get update
        apt-get install -y chromium-browser
    fi

    # Create kiosk user if not exists
    KIOSK_USER="poolaissistant"
    if ! id "$KIOSK_USER" &>/dev/null; then
        useradd -m -s /bin/bash "$KIOSK_USER"
        usermod -a -G video,input,audio "$KIOSK_USER"
    fi

    # Create kiosk startup script
    KIOSK_SCRIPT="/home/$KIOSK_USER/start_kiosk.sh"
    cat > "$KIOSK_SCRIPT" << 'EOF'
#!/bin/bash
# PoolAIssistant Kiosk Startup Script

# Wait for network
sleep 5

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide mouse cursor after 3 seconds of inactivity
unclutter -idle 3 &

# Start Chromium in kiosk mode
chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --disable-translate \
    --no-first-run \
    --fast \
    --fast-start \
    --disable-features=TranslateUI \
    --check-for-update-interval=31536000 \
    --overscroll-history-navigation=0 \
    --enable-features=OverlayScrollbar,TouchpadAndWheelScrollLatching \
    --touch-events=enabled \
    --enable-touch-drag-drop \
    --enable-touchview \
    "http://localhost"
EOF
    chmod +x "$KIOSK_SCRIPT"
    chown "$KIOSK_USER:$KIOSK_USER" "$KIOSK_SCRIPT"

    # Create systemd service for kiosk
    KIOSK_SERVICE="/etc/systemd/system/poolaissistant_kiosk.service"
    cat > "$KIOSK_SERVICE" << EOF
[Unit]
Description=PoolAIssistant Kiosk Browser
After=poolaissistant_ui.service
Wants=poolaissistant_ui.service

[Service]
Type=simple
User=$KIOSK_USER
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/startx /home/$KIOSK_USER/start_kiosk.sh -- -nocursor
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable poolaissistant_kiosk

    # Install dependencies
    apt-get install -y xserver-xorg xinit unclutter || true

    log_info "  Kiosk mode configured - browser will start on boot"
fi

# ============================================
# 8. OPTIMIZE FOR EMBEDDED USE
# ============================================
log_info "Optimizing for embedded use..."

# Reduce logging to minimize SD card writes
if [ -f "/etc/systemd/journald.conf" ]; then
    sed -i 's/#Storage=auto/Storage=volatile/' /etc/systemd/journald.conf
    sed -i 's/#RuntimeMaxUse=/RuntimeMaxUse=50M/' /etc/systemd/journald.conf
    log_info "  Configured journald for volatile storage"
fi

# Create tmpfs for temporary files
if ! grep -q "tmpfs /tmp" /etc/fstab; then
    echo "tmpfs /tmp tmpfs defaults,noatime,nosuid,size=100m 0 0" >> /etc/fstab
    log_info "  Added tmpfs for /tmp"
fi

# ============================================
# SUMMARY
# ============================================
echo
echo "========================================"
echo " Setup Complete!"
echo "========================================"
echo
echo "The following has been configured:"
echo "  - SSH enabled for remote access"
echo "  - PoolAIssistant services enabled"
echo "  - Desktop environment disabled"
echo "  - Bluetooth disabled"
echo "  - Touchscreen scrolling configured"
echo "  - Unneeded services disabled"
if [ "$WITH_BROWSER" = true ]; then
    echo "  - Chromium kiosk mode enabled"
fi
echo
echo "The web UI will be available at:"
echo "  http://<pi-ip-address>"
echo
log_warn "A reboot is required for all changes to take effect."
echo
read -p "Reboot now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    reboot
fi
