# PoolAIssistant Raspberry Pi Setup Guide

Complete guide for setting up a fresh Raspberry Pi for PoolAIssistant.

## Prerequisites

- Raspberry Pi 4 or 5 (2GB+ RAM recommended)
- MicroSD card (16GB+ recommended)
- Raspberry Pi OS Lite (64-bit) - Bookworm or newer
- Ethernet connection for initial setup (recommended)
- WiFi network details (SSID and password)

## 1. Initial Pi Setup

### Flash Raspberry Pi OS

1. Download Raspberry Pi Imager: https://www.raspberrypi.com/software/
2. Flash "Raspberry Pi OS Lite (64-bit)" to SD card
3. In Imager settings (gear icon):
   - Set hostname: `poolaissistant`
   - Enable SSH with password authentication
   - Set username: `poolai`
   - Set password: `12345678` (change this later!)
   - Configure WiFi (optional, can do later)
   - Set locale/timezone

### First Boot

```bash
# Connect via SSH (ethernet or configured WiFi)
ssh poolai@poolaissistant.local
# Or use IP: ssh poolai@<ip-address>

# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    python3 python3-pip python3-venv \
    hostapd dnsmasq \
    network-manager \
    wireless-tools \
    avahi-daemon \
    nginx \
    git \
    chromium-browser \
    wlr-randr \
    fail2ban

# Disable hostapd/dnsmasq auto-start (managed by AP manager)
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
```

## 2. Install PoolAIssistant

### Create Directory Structure

```bash
sudo mkdir -p /opt/PoolAIssistant/{app,data}
sudo chown -R poolai:poolai /opt/PoolAIssistant
```

### Copy Application Files

```bash
# From your development machine, SCP the files:
scp -r PoolDash_v6/* poolai@poolaissistant.local:/opt/PoolAIssistant/app/

# Or clone from git:
cd /opt/PoolAIssistant
git clone https://github.com/bensalmon91-cpu/poolaissistant-.git app
```

### Install Python Dependencies

```bash
cd /opt/PoolAIssistant/app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# For GPIO button support (optional)
pip install RPi.GPIO
```

### Install System Scripts

```bash
# Make scripts executable
chmod +x /opt/PoolAIssistant/app/scripts/*.sh
chmod +x /opt/PoolAIssistant/app/scripts/*.py
chmod +x /opt/PoolAIssistant/app/deploy/*.sh

# Create symlinks for system access
sudo ln -sf /opt/PoolAIssistant/app/scripts/update_wifi.sh /usr/local/bin/
sudo ln -sf /opt/PoolAIssistant/app/scripts/update_ethernet.sh /usr/local/bin/
sudo ln -sf /opt/PoolAIssistant/app/scripts/network_reset.sh /usr/local/bin/
sudo ln -sf /opt/PoolAIssistant/app/scripts/poolaissistant_ap_manager.sh /usr/local/bin/
```

### Configure Sudoers

```bash
# Allow poolai to run network scripts without password
sudo tee /etc/sudoers.d/poolaissistant << 'EOF'
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
sudo chmod 440 /etc/sudoers.d/poolaissistant
```

## 3. Configure Services

### Install Systemd Services

```bash
# Copy service files
sudo cp /opt/PoolAIssistant/app/scripts/systemd/*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable poolaissistant_ui.service
sudo systemctl enable poolaissistant_logger.service
sudo systemctl enable poolaissistant_ap_manager.service
sudo systemctl enable poolaissistant_button.service  # Optional - physical button

# Start services
sudo systemctl start poolaissistant_ap_manager.service
sudo systemctl start poolaissistant_ui.service
sudo systemctl start poolaissistant_logger.service
```

### Configure Nginx (Port 80 Proxy)

```bash
sudo tee /etc/nginx/sites-available/poolaissistant << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30;
        proxy_read_timeout 300;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/poolaissistant /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
sudo systemctl enable nginx
```

## 4. Physical Button Setup (Optional)

The physical button provides emergency network reset capability.

### Wiring

Connect a momentary push button:
- One terminal to **GPIO3** (Pin 5)
- Other terminal to **Ground** (Pin 6)

GPIO3 is special - it can also wake the Pi from halt state.

### Button Functions

| Press Duration | Action |
|---------------|--------|
| < 2 seconds | Show network status (logs) |
| 5-10 seconds | Reset network settings, enable AP |
| > 10 seconds | Full factory reset |

### Enable Button Service

```bash
sudo systemctl enable poolaissistant_button.service
sudo systemctl start poolaissistant_button.service
```

## 5. Kiosk Mode Setup (Touchscreen Display)

For Pi with official touchscreen:

### Install Display Packages

```bash
sudo apt install -y \
    labwc \
    seatd \
    xwayland \
    chromium-browser
```

### Configure Auto-Login

```bash
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin poolai --noclear %I $TERM
EOF
```

### Create Kiosk Startup Script

```bash
tee ~/.bash_profile << 'EOF'
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec labwc
fi
EOF

mkdir -p ~/.config/labwc
tee ~/.config/labwc/autostart << 'EOF'
chromium-browser --kiosk --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --disable-restore-session-state \
    --no-first-run http://localhost &
EOF
```

## 6. Network Configuration

### Access Point Settings

The AP manager automatically:
- Starts AP on boot for 5 minutes (user access)
- Checks WiFi connectivity every 10 seconds
- Turns off AP when WiFi is connected and stable
- Immediately restarts AP if WiFi drops

Default AP credentials:
- **SSID:** PoolAId
- **Password:** 12345678
- **IP:** 192.168.4.1

### Customize AP Settings

Create `/opt/PoolAIssistant/data/ap_config.sh`:

```bash
# Custom AP configuration
AP_SSID="MyPoolAP"
AP_PSK="mysecurepassword"
INITIAL_AP_TIME=600  # 10 minutes
```

## 7. Verify Installation

### Check Services

```bash
sudo systemctl status poolaissistant_ui
sudo systemctl status poolaissistant_logger
sudo systemctl status poolaissistant_ap_manager
```

### Test Web Interface

1. Connect to PoolAId WiFi (password: 12345678)
2. Browse to http://192.168.4.1
3. Configure WiFi in Settings
4. Device will connect to your network

### View Logs

```bash
# UI service logs
sudo journalctl -u poolaissistant_ui -f

# AP manager logs
sudo journalctl -u poolaissistant_ap_manager -f

# All PoolAIssistant logs
sudo journalctl -u 'poolaissistant_*' -f
```

## 8. Prepare for Cloning

Once everything is configured and tested:

```bash
sudo /opt/PoolAIssistant/app/deploy/clone_prep.sh
```

This will:
- Stop all services
- Clear databases and settings
- Remove SSH keys
- Forget all WiFi networks
- Create first-boot marker
- Prepare for SD card imaging

Then shutdown and clone the SD card.

## Troubleshooting

### Device Not Accessible

1. **Check if AP is running:**
   ```bash
   sudo systemctl status hostapd
   ```

2. **Force AP mode:**
   ```bash
   sudo /usr/local/bin/network_reset.sh
   ```

3. **Physical button:** Hold for 5+ seconds to reset network

### WiFi Not Connecting

1. Check WiFi is enabled:
   ```bash
   nmcli radio wifi
   ```

2. Scan for networks:
   ```bash
   nmcli device wifi list
   ```

3. Manual connect:
   ```bash
   sudo nmcli device wifi connect "SSID" password "PASSWORD"
   ```

### Services Not Starting

```bash
# Check for errors
sudo journalctl -u poolaissistant_ui -n 50

# Check Python environment
/opt/PoolAIssistant/app/venv/bin/python --version

# Test Flask app directly
cd /opt/PoolAIssistant/app
./venv/bin/python -m flask run --host=0.0.0.0 --port=8080
```

### Permission Errors

```bash
# Fix ownership
sudo chown -R poolai:poolai /opt/PoolAIssistant

# Check sudoers
sudo visudo -c
sudo cat /etc/sudoers.d/poolaissistant
```

## Security Recommendations

After deployment, change these default credentials:

1. **SSH Password:** `passwd` to change from 12345678
2. **AP Password:** Edit `/opt/PoolAIssistant/data/ap_config.sh`
3. **Settings Password:** (Currently hardcoded as PoolAI)

Enable fail2ban for SSH protection:
```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## Quick Reference

| Item | Value |
|------|-------|
| Default user | poolai |
| Default password | 12345678 |
| AP SSID | PoolAId |
| AP IP | 192.168.4.1 |
| Web UI | http://poolaissistant.local or http://<ip> |
| Settings password | PoolAI |
| App directory | /opt/PoolAIssistant/app |
| Data directory | /opt/PoolAIssistant/data |
| Logs | `journalctl -u poolaissistant_*` |
