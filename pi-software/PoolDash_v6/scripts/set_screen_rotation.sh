#!/bin/bash
# set_screen_rotation.sh - Rotate display and touchscreen on Raspberry Pi
# Usage: sudo ./set_screen_rotation.sh <degrees>
# Where degrees is 0, 90, 180, or 270

# Note: Removed 'set -e' for explicit error handling

ROTATION="${1:-0}"
SCRIPT_OUTPUT=""

# Log function that also captures output for the web UI
log() {
    echo "$1"
    SCRIPT_OUTPUT="${SCRIPT_OUTPUT}${1}\n"
}

log_error() {
    echo "ERROR: $1" >&2
    SCRIPT_OUTPUT="${SCRIPT_OUTPUT}ERROR: ${1}\n"
}

# Validate rotation value
if [[ ! "$ROTATION" =~ ^(0|90|180|270)$ ]]; then
    log_error "Rotation must be 0, 90, 180, or 270"
    exit 1
fi

# Map rotation degrees to config.txt display_lcd_rotate value
# 0=normal, 1=90°, 2=180°, 3=270°
case "$ROTATION" in
    0)   LCD_ROTATE=0 ;;
    90)  LCD_ROTATE=1 ;;
    180) LCD_ROTATE=2 ;;
    270) LCD_ROTATE=3 ;;
esac

# Determine which config file to use (modern vs legacy Pi OS)
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
else
    log_error "Could not find config.txt"
    exit 1
fi

log "Setting screen rotation to ${ROTATION}° (lcd_rotate=${LCD_ROTATE})"
log "Config file: ${CONFIG_FILE}"

# Backup config file
cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

# Remove existing rotation settings (using # delimiter to avoid issues)
sed -i '#^display_lcd_rotate=#d' "$CONFIG_FILE" 2>/dev/null || \
    sed -i '/^display_lcd_rotate=/d' "$CONFIG_FILE"
sed -i '#^lcd_rotate=#d' "$CONFIG_FILE" 2>/dev/null || \
    sed -i '/^lcd_rotate=/d' "$CONFIG_FILE"
sed -i '#^display_rotate=#d' "$CONFIG_FILE" 2>/dev/null || \
    sed -i '/^display_rotate=/d' "$CONFIG_FILE"
sed -i '#^dtoverlay=vc4-kms-v3d,rotation=#d' "$CONFIG_FILE" 2>/dev/null || \
    sed -i '/^dtoverlay=vc4-kms-v3d,rotation=/d' "$CONFIG_FILE"

# Add the rotation setting
# For official Raspberry Pi touchscreen on Pi 5
if grep -q "dtoverlay=vc4-kms-v3d" "$CONFIG_FILE"; then
    # Modern KMS driver - use display_lcd_rotate
    echo "display_lcd_rotate=${LCD_ROTATE}" >> "$CONFIG_FILE"
else
    # Legacy or other setups
    echo "lcd_rotate=${LCD_ROTATE}" >> "$CONFIG_FILE"
fi

log "Config file updated."

# ========================================
# Find the display user and Wayland socket
# ========================================

# Get the home directory for a user (handles non-standard home locations)
get_user_home() {
    local user="$1"
    local home_dir

    # Try getent first (most reliable)
    home_dir=$(getent passwd "$user" 2>/dev/null | cut -d: -f6)
    if [ -n "$home_dir" ] && [ -d "$home_dir" ]; then
        echo "$home_dir"
        return 0
    fi

    # Fallback to eval ~user
    home_dir=$(eval echo "~$user" 2>/dev/null)
    if [ -n "$home_dir" ] && [ -d "$home_dir" ]; then
        echo "$home_dir"
        return 0
    fi

    # Last resort: assume /home/$user
    echo "/home/$user"
}

find_display_user() {
    # Method 1: Check who is logged in on tty or :0
    local user=$(who | grep -E 'tty|:0' | head -1 | awk '{print $1}')
    if [ -n "$user" ] && id "$user" &>/dev/null; then
        echo "$user"
        return 0
    fi

    # Method 2: Check for active graphical session
    for dir in /run/user/*; do
        if [ -d "$dir" ]; then
            local uid=$(basename "$dir")
            local check_user=$(getent passwd "$uid" 2>/dev/null | cut -d: -f1)
            if [ -n "$check_user" ]; then
                # Check if this user has a wayland socket
                if ls "$dir"/wayland-* &>/dev/null; then
                    echo "$check_user"
                    return 0
                fi
            fi
        fi
    done

    # Method 3: Try common kiosk users
    for try_user in poolai pi kiosk; do
        if id "$try_user" &>/dev/null; then
            local uid=$(id -u "$try_user")
            if [ -d "/run/user/$uid" ]; then
                echo "$try_user"
                return 0
            fi
        fi
    done

    # Method 4: Try to find any user running a Wayland compositor
    local compositor_pid=$(pgrep -x "labwc\|weston\|sway" 2>/dev/null | head -1)
    if [ -n "$compositor_pid" ]; then
        local comp_user=$(ps -o user= -p "$compositor_pid" 2>/dev/null)
        if [ -n "$comp_user" ] && id "$comp_user" &>/dev/null; then
            echo "$comp_user"
            return 0
        fi
    fi

    # No user found - return empty and let caller handle
    echo ""
    return 1
}

find_wayland_socket() {
    local runtime_dir="$1"

    # Look for any wayland socket (wayland-0, wayland-1, etc.)
    for socket in "$runtime_dir"/wayland-*; do
        if [ -S "$socket" ]; then
            # Verify socket is still valid
            if [ -S "$socket" ]; then
                basename "$socket"
                return 0
            fi
        fi
    done
    return 1
}

# Find the display user
DISPLAY_USER=$(find_display_user)
if [ -z "$DISPLAY_USER" ]; then
    log "Warning: Could not detect display user, trying 'poolai'"
    DISPLAY_USER="poolai"
    if ! id "$DISPLAY_USER" &>/dev/null; then
        DISPLAY_USER="pi"
        if ! id "$DISPLAY_USER" &>/dev/null; then
            log_error "Cannot find a valid display user (tried poolai, pi)"
            # Continue anyway - rotation will be applied on reboot
        fi
    fi
fi

# Get the user's UID - must succeed for immediate rotation
USER_UID=$(id -u "$DISPLAY_USER" 2>/dev/null)
if [ -z "$USER_UID" ]; then
    log_error "Cannot determine UID for user $DISPLAY_USER"
    log "Rotation will be applied on next reboot."
    USER_UID=""
fi

if [ -n "$USER_UID" ]; then
    XDG_RUNTIME_DIR="/run/user/$USER_UID"
    log "Display user: $DISPLAY_USER (uid: $USER_UID)"
    log "XDG_RUNTIME_DIR: $XDG_RUNTIME_DIR"
else
    XDG_RUNTIME_DIR=""
fi

# Get user's home directory for Xauthority
USER_HOME=$(get_user_home "$DISPLAY_USER")
log "User home: $USER_HOME"

# ========================================
# Apply rotation immediately
# ========================================

ROTATION_APPLIED=false

# Check for Wayland (labwc/wlroots on newer Pi OS)
if [ -n "$XDG_RUNTIME_DIR" ] && command -v wlr-randr &> /dev/null; then
    WAYLAND_SOCKET=$(find_wayland_socket "$XDG_RUNTIME_DIR")

    if [ -n "$WAYLAND_SOCKET" ]; then
        # Verify socket still exists before using
        if [ -S "$XDG_RUNTIME_DIR/$WAYLAND_SOCKET" ]; then
            log "Found Wayland socket: $WAYLAND_SOCKET"
            log "Attempting Wayland rotation with wlr-randr..."

            case "$ROTATION" in
                0)   TRANSFORM="normal" ;;
                90)  TRANSFORM="90" ;;
                180) TRANSFORM="180" ;;
                270) TRANSFORM="270" ;;
            esac

            # Try to get the output name - look for common display output patterns
            OUTPUT=$(sudo -u "$DISPLAY_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$WAYLAND_SOCKET" wlr-randr 2>/dev/null | \
                grep -E "^(HDMI|DP|eDP|DSI|DPI|LVDS|VGA)" | head -1 | awk '{print $1}' || true)

            # Fallback: try any line starting with uppercase that looks like an output
            if [ -z "$OUTPUT" ]; then
                OUTPUT=$(sudo -u "$DISPLAY_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$WAYLAND_SOCKET" wlr-randr 2>/dev/null | \
                    grep -E "^[A-Z].*[0-9]" | head -1 | awk '{print $1}' || true)
            fi

            if [ -n "$OUTPUT" ]; then
                log "Found output: $OUTPUT"
                if sudo -u "$DISPLAY_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$WAYLAND_SOCKET" wlr-randr --output "$OUTPUT" --transform "$TRANSFORM" 2>&1; then
                    log "Applied Wayland rotation to $OUTPUT"
                    ROTATION_APPLIED=true
                else
                    log "Warning: wlr-randr command failed"
                fi
            else
                log "Warning: Could not detect Wayland output"
            fi
        else
            log "Warning: Wayland socket disappeared before use"
        fi
    else
        log "No Wayland socket found in $XDG_RUNTIME_DIR"
    fi
fi

# Fallback to X11 if Wayland didn't work
if [ "$ROTATION_APPLIED" = false ] && command -v xrandr &> /dev/null; then
    log "Attempting X11 rotation with xrandr..."
    case "$ROTATION" in
        0)   XROTATE="normal" ;;
        90)  XROTATE="right" ;;
        180) XROTATE="inverted" ;;
        270) XROTATE="left" ;;
    esac

    # Get primary output
    OUTPUT=$(sudo -u "$DISPLAY_USER" DISPLAY=:0 xrandr 2>/dev/null | grep " connected" | head -1 | awk '{print $1}' || true)
    if [ -n "$OUTPUT" ]; then
        # Find Xauthority file - check multiple locations
        XAUTH_FILE=""
        for auth_path in "$USER_HOME/.Xauthority" "/run/user/$USER_UID/gdm/Xauthority" "/tmp/.X0-lock"; do
            if [ -f "$auth_path" ]; then
                XAUTH_FILE="$auth_path"
                break
            fi
        done

        if [ -z "$XAUTH_FILE" ]; then
            XAUTH_FILE="$USER_HOME/.Xauthority"
        fi

        if sudo -u "$DISPLAY_USER" DISPLAY=:0 XAUTHORITY="$XAUTH_FILE" xrandr --output "$OUTPUT" --rotate "$XROTATE" 2>&1; then
            log "Applied X11 rotation to $OUTPUT"
            ROTATION_APPLIED=true
        else
            log "Warning: xrandr command failed"
        fi
    else
        log "Warning: No X11 output found"
    fi
fi

if [ "$ROTATION_APPLIED" = false ]; then
    log "Warning: Could not apply rotation immediately. Reboot required."
fi

# ========================================
# Configure touchscreen calibration
# ========================================

log "Configuring touchscreen input rotation..."

case "$ROTATION" in
    0)   MATRIX="1 0 0 0 1 0" ;;       # Identity matrix
    90)  MATRIX="0 1 0 -1 0 1" ;;      # 90° clockwise
    180) MATRIX="-1 0 1 0 -1 1" ;;     # 180°
    270) MATRIX="0 -1 1 1 0 0" ;;      # 270° (90° counter-clockwise)
esac

# Create/update libinput quirks for touchscreen rotation
QUIRKS_DIR="/etc/libinput"
QUIRKS_FILE="${QUIRKS_DIR}/local-overrides.quirks"

mkdir -p "$QUIRKS_DIR" 2>/dev/null || true

# Try to find the touchscreen device
TOUCH_DEVICE=$(grep -l -r "touchscreen\|FT5406\|Goodix\|eGalax\|ELAN\|ADS7846" /sys/class/input/*/name 2>/dev/null | head -1 || true)
if [ -n "$TOUCH_DEVICE" ]; then
    TOUCH_NAME=$(cat "$TOUCH_DEVICE" 2>/dev/null || echo "Unknown")
    log "Found touchscreen: $TOUCH_NAME"
else
    log "No touchscreen detected - calibration may not apply (this is normal for HDMI displays)"
fi

# Write calibration to Xorg config (for X11)
XORG_CONF="/etc/X11/xorg.conf.d/99-touchscreen-rotation.conf"
mkdir -p /etc/X11/xorg.conf.d 2>/dev/null || true
cat > "$XORG_CONF" << EOF
Section "InputClass"
    Identifier "Touchscreen rotation"
    MatchIsTouchscreen "on"
    Option "CalibrationMatrix" "${MATRIX} 0 0 1"
EndSection
EOF

log "Touchscreen calibration configured."
log ""
log "=== ROTATION COMPLETE ==="
log "Display rotation: ${ROTATION}°"
if [ "$ROTATION_APPLIED" = true ]; then
    log "Rotation applied immediately."
else
    log "A REBOOT is required for rotation to take effect."
fi
log "Touchscreen calibration may require a reboot."
