# PoolAIssistant Pi Clone Donor - Reinstall Plan

## What Went Wrong (Lessons Learned)

1. **WiFi disconnection killed SSH session** - The clone_prep.sh removes WiFi networks mid-script, which killed the remote SSH session before the script completed
2. **SSH keys weren't preserved** - The authorized_keys file wasn't backed up before clone_prep ran
3. **Password auth was broken** - The SSH config may have been corrupted or the service didn't restart properly
4. **Script ran remotely** - Running clone_prep over SSH is risky because the script modifies network and SSH settings

## Pre-requisites

Before starting:
- Fresh Raspberry Pi OS flashed to SD card (64-bit Lite)
- Pi connected via **Ethernet** (not WiFi - more stable for setup)
- SSH enabled during Pi Imager setup
- User: `poolai`, Password: `12345678`

## Step-by-Step Reinstall Process

### Phase 1: Initial Connection (via Ethernet)
```powershell
# From Windows, find the Pi
ping poolaissistant.local

# SSH in (will be prompted for password: 12345678)
ssh poolai@<pi-ip>
```

### Phase 2: System Setup (run on Pi)
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    python3-pip python3-venv \
    hostapd dnsmasq network-manager \
    wireless-tools avahi-daemon nginx \
    git wlr-randr fail2ban

# Disable hostapd/dnsmasq auto-start
sudo systemctl disable hostapd dnsmasq
sudo systemctl stop hostapd dnsmasq
sudo systemctl unmask hostapd
```

### Phase 3: Upload Software (from Windows)
```powershell
# Create directories
ssh poolai@<pi-ip> "sudo mkdir -p /opt/PoolAIssistant/{app,data} && sudo chown -R poolai:poolai /opt/PoolAIssistant"

# Upload software
scp -r "C:/Users/bensa/iCloudDrive/MBSoftware/PoolAIssistant-Project/pi-software/PoolDash_v6/"* poolai@<pi-ip>:/opt/PoolAIssistant/app/
```

### Phase 4: Install Dependencies (run on Pi)
```bash
# Create venv and install Python packages
python3 -m venv /opt/PoolAIssistant/venv
source /opt/PoolAIssistant/venv/bin/activate
pip install --upgrade pip
pip install -r /opt/PoolAIssistant/app/requirements.txt

# Make scripts executable
chmod +x /opt/PoolAIssistant/app/scripts/*.sh /opt/PoolAIssistant/app/scripts/*.py
chmod +x /opt/PoolAIssistant/app/deploy/*.sh
```

### Phase 5: Configure Services (run on Pi)
```bash
# Create environment file
sudo mkdir -p /etc/PoolAIssistant
sudo tee /etc/PoolAIssistant/poolaissistant.env > /dev/null << 'EOF'
FLASK_APP=pooldash_app
FLASK_ENV=production
DATA_DIR=/opt/PoolAIssistant/data
APP_DIR=/opt/PoolAIssistant/app
EOF

# Install systemd services
sudo cp /opt/PoolAIssistant/app/scripts/systemd/*.service /opt/PoolAIssistant/app/scripts/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable poolaissistant_ui.service poolaissistant_logger.service poolaissistant_ap_manager.service poolaissistant_provision.service

# Create script symlinks
sudo ln -sf /opt/PoolAIssistant/app/scripts/update_wifi.sh /usr/local/bin/
sudo ln -sf /opt/PoolAIssistant/app/scripts/update_ethernet.sh /usr/local/bin/
sudo ln -sf /opt/PoolAIssistant/app/scripts/network_reset.sh /usr/local/bin/
sudo ln -sf /opt/PoolAIssistant/app/scripts/poolaissistant_ap_manager.sh /usr/local/bin/

# Configure sudoers
sudo tee /etc/sudoers.d/poolaissistant > /dev/null << 'EOF'
poolai ALL=(ALL) NOPASSWD: ALL
EOF
sudo chmod 440 /etc/sudoers.d/poolaissistant
```

### Phase 6: Configure Nginx (run on Pi)
```bash
sudo tee /etc/nginx/sites-available/poolaissistant > /dev/null << 'EOF'
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
```

### Phase 7: Set Up Persistent SSH Access (IMPORTANT - run on Pi)
```bash
# Set hostname
sudo hostnamectl set-hostname poolaissistant
echo 'poolaissistant' | sudo tee /etc/hostname
sudo sed -i 's/127\.0\.1\.1.*/127.0.1.1\tpoolaissistant/' /etc/hosts

# Enable SSH permanently
sudo systemctl enable ssh avahi-daemon fail2ban
sudo systemctl start ssh avahi-daemon fail2ban

# Configure fail2ban
sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ssh
maxretry = 3
bantime = 1h
EOF
sudo systemctl restart fail2ban

# Create SSH key backup directory
mkdir -p /opt/PoolAIssistant/data/admin

# IMPORTANT: Add your SSH public key
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICT2USTN90TYd32Y6iQf7RW9q/AGYULgAv1RVykZhxuk claude-pi" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Backup authorized_keys (survives clone prep)
cp ~/.ssh/authorized_keys /opt/PoolAIssistant/data/admin/ssh_authorized_keys_backup

# Create SSH restore service
sudo tee /etc/systemd/system/poolaissistant_ssh_restore.service > /dev/null << 'SERVICE'
[Unit]
Description=Restore SSH authorized_keys after clone
After=ssh.service
ConditionPathExists=/opt/PoolAIssistant/data/admin/ssh_authorized_keys_backup

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'mkdir -p /home/poolai/.ssh && chmod 700 /home/poolai/.ssh && cp /opt/PoolAIssistant/data/admin/ssh_authorized_keys_backup /home/poolai/.ssh/authorized_keys && chmod 600 /home/poolai/.ssh/authorized_keys && chown -R poolai:poolai /home/poolai/.ssh'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE
sudo systemctl daemon-reload
sudo systemctl enable poolaissistant_ssh_restore.service
```

### Phase 8: Test Everything (run on Pi)
```bash
# Start services
sudo systemctl start poolaissistant_ui

# Check it's running
sudo systemctl status poolaissistant_ui

# Test web UI
curl -s http://localhost/ | head -5
```

### Phase 9: Run Clone Prep (LOCALLY ON PI - NOT OVER SSH!)

**CRITICAL: Run clone_prep from a local terminal (monitor+keyboard) NOT over SSH!**

```bash
# The safe way to run clone prep:
sudo /opt/PoolAIssistant/app/deploy/clone_prep_safe.sh
```

Use the new `clone_prep_safe.sh` which:
1. Does network-breaking tasks LAST
2. Preserves SSH authorized_keys backup
3. Ensures SSH will work after clone

### Phase 10: Create SD Card Image
```bash
# Shutdown cleanly
sudo shutdown -h now

# Remove SD card and clone with Win32DiskImager or dd
```

## Emergency Recovery

If you get locked out:
1. Connect monitor+keyboard to Pi
2. Login as poolai (password: 12345678)
3. Run: `/opt/PoolAIssistant/app/scripts/emergency_ssh_restore.sh`

## Files Created/Modified

- `/opt/PoolAIssistant/app/` - Application code
- `/opt/PoolAIssistant/data/` - Data and settings
- `/opt/PoolAIssistant/data/admin/ssh_authorized_keys_backup` - SSH key backup
- `/opt/PoolAIssistant/venv/` - Python virtual environment
- `/etc/PoolAIssistant/poolaissistant.env` - Environment variables
- `/etc/systemd/system/poolaissistant_*.service` - Systemd services
- `/etc/nginx/sites-available/poolaissistant` - Nginx config
- `/etc/sudoers.d/poolaissistant` - Sudo permissions
- `/etc/fail2ban/jail.local` - Fail2ban config
