#!/usr/bin/env bash
# ensure_dependencies.sh
# Checks and installs required system packages for PoolAIssistant
# Also sets up script symlinks and permissions
# Run as root or via sudo

set -euo pipefail

LOG_FILE="/var/log/poolaissistant_deps.log"
APP_DIR="/opt/PoolAIssistant/app"
DATA_DIR="/opt/PoolAIssistant/data"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

# Required packages for WiFi AP and network management
REQUIRED_PACKAGES=(
    "hostapd"
    "dnsmasq"
    "network-manager"
    "wireless-tools"
    "avahi-daemon"
    "iputils-ping"
)

# Optional but recommended packages
OPTIONAL_PACKAGES=(
    "iw"
    "wpasupplicant"
    "fail2ban"
)

install_missing() {
    local missing=()

    # Check which packages are missing
    for pkg in "${REQUIRED_PACKAGES[@]}"; do
        if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            missing+=("$pkg")
        fi
    done

    if [ ${#missing[@]} -eq 0 ]; then
        log "All required packages are already installed."
        return 0
    fi

    log "Missing packages: ${missing[*]}"
    log "Updating package lists..."

    apt-get update -qq

    log "Installing missing packages..."
    for pkg in "${missing[@]}"; do
        log "Installing $pkg..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg" || {
            log "WARNING: Failed to install $pkg"
        }
    done

    # Configure hostapd to not start automatically (managed by our AP manager)
    if systemctl is-enabled hostapd 2>/dev/null | grep -q "enabled"; then
        systemctl disable hostapd 2>/dev/null || true
        systemctl stop hostapd 2>/dev/null || true
        log "Disabled hostapd auto-start (managed by AP manager)"
    fi

    # Same for dnsmasq
    if systemctl is-enabled dnsmasq 2>/dev/null | grep -q "enabled"; then
        systemctl disable dnsmasq 2>/dev/null || true
        systemctl stop dnsmasq 2>/dev/null || true
        log "Disabled dnsmasq auto-start (managed by AP manager)"
    fi

    log "Dependency installation complete."
}

# Create necessary directories
ensure_directories() {
    mkdir -p /etc/hostapd
    mkdir -p /etc/dnsmasq.d
    mkdir -p "$DATA_DIR"
    log "Directories verified."
}

# Set up script symlinks
setup_scripts() {
    local scripts_dir="$APP_DIR/scripts"

    # Scripts that need to be accessible via sudo
    local scripts=(
        "update_wifi.sh"
        "update_ethernet.sh"
        "network_reset.sh"
        "poolaissistant_ap_manager.sh"
    )

    for script in "${scripts[@]}"; do
        if [ -f "$scripts_dir/$script" ]; then
            chmod +x "$scripts_dir/$script"
            ln -sf "$scripts_dir/$script" "/usr/local/bin/$script"
            log "Linked: $script"
        fi
    done

    # Make all scripts executable
    find "$scripts_dir" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
    find "$scripts_dir" -name "*.py" -exec chmod +x {} \; 2>/dev/null || true

    log "Scripts configured."
}

# Configure sudoers for poolai user
setup_sudoers() {
    local sudoers_file="/etc/sudoers.d/poolaissistant"

    # Only create if poolai user exists
    if ! id poolai >/dev/null 2>&1; then
        log "User 'poolai' not found, skipping sudoers setup"
        return 0
    fi

    cat > "$sudoers_file" << 'EOF'
# PoolAIssistant sudoers configuration
poolai ALL=(ALL) NOPASSWD: /usr/local/bin/update_wifi.sh
poolai ALL=(ALL) NOPASSWD: /usr/local/bin/update_ethernet.sh
poolai ALL=(ALL) NOPASSWD: /usr/local/bin/network_reset.sh
poolai ALL=(ALL) NOPASSWD: /sbin/reboot
poolai ALL=(ALL) NOPASSWD: /bin/systemctl restart poolaissistant_*
poolai ALL=(ALL) NOPASSWD: /bin/systemctl start poolaissistant_*
poolai ALL=(ALL) NOPASSWD: /bin/systemctl stop poolaissistant_*
poolai ALL=(ALL) NOPASSWD: /bin/systemctl restart hostapd
poolai ALL=(ALL) NOPASSWD: /bin/systemctl restart dnsmasq
poolai ALL=(ALL) NOPASSWD: /bin/systemctl start hostapd
poolai ALL=(ALL) NOPASSWD: /bin/systemctl start dnsmasq
poolai ALL=(ALL) NOPASSWD: /bin/systemctl stop hostapd
poolai ALL=(ALL) NOPASSWD: /bin/systemctl stop dnsmasq
poolai ALL=(ALL) NOPASSWD: /usr/bin/ssh-keygen -A
poolai ALL=(ALL) NOPASSWD: /bin/systemctl * ssh
EOF
    chmod 440 "$sudoers_file"
    log "Sudoers configured."
}

# Install/update systemd services
setup_services() {
    local services_dir="$APP_DIR/scripts/systemd"

    if [ ! -d "$services_dir" ]; then
        log "Systemd services directory not found"
        return 0
    fi

    # Copy service files
    for service in "$services_dir"/*.service; do
        if [ -f "$service" ]; then
            cp "$service" /etc/systemd/system/
            log "Installed service: $(basename "$service")"
        fi
    done

    systemctl daemon-reload
    log "Systemd services updated."
}

# Install daily maintenance cron job
setup_cron() {
    local cron_src="$APP_DIR/deploy/poolaissistant-maintenance"
    local cron_dst="/etc/cron.daily/poolaissistant-maintenance"

    if [ -f "$cron_src" ]; then
        cp "$cron_src" "$cron_dst"
        chmod +x "$cron_dst"
        log "Installed daily maintenance cron job"
    else
        log "Maintenance cron script not found at $cron_src"
    fi

    # Create backup directory
    mkdir -p /opt/PoolAIssistant/backups
    chown poolaissistant:poolaissistant /opt/PoolAIssistant/backups 2>/dev/null || true
    log "Backup directory created"
}

# Main
log "=== PoolAIssistant Dependency Check ==="

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root" >&2
    exit 1
fi

ensure_directories
install_missing
setup_scripts
setup_sudoers
setup_services
setup_cron

log "=== Dependency check complete ==="
