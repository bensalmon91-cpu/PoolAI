# PoolAIssistant Pi Hardening Guide

This guide covers security hardening for production Pi deployments.

## 1. Read-Only Root Filesystem

Making the root filesystem read-only prevents corruption from power loss and limits attack surface.

### Enable Overlay Filesystem

```bash
# Install overlay tools
sudo apt install -y overlayroot

# Edit overlay config
sudo nano /etc/overlayroot.conf

# Set:
overlayroot="tmpfs:swap=1,recurse=0"

# Reboot
sudo reboot
```

### Alternative: raspi-config

```bash
sudo raspi-config
# Performance Options > Overlay File System > Enable
# Also enable "Write-protect boot partition"
```

### Keep /opt/PoolAIssistant/data Writable

Create a separate partition or use tmpfs with persistence:

```bash
# Add to /etc/fstab before enabling overlay:
tmpfs /opt/PoolAIssistant/data tmpfs defaults,noatime,size=500M 0 0
```

Or use a persistent USB drive:
```bash
/dev/sda1 /opt/PoolAIssistant/data ext4 defaults,noatime 0 2
```

---

## 2. SSH Hardening

### Disable Password Auth

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Set these values:
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers poolaissistant

# Restart SSH
sudo systemctl restart sshd
```

### Use Key-Based Auth Only

Generate key on your PC:
```bash
ssh-keygen -t ed25519 -C "poolaissistant-admin"
```

Copy to Pi:
```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub poolai@<pi-ip>
```

### Fail2Ban

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
```

---

## 3. Firewall Setup

```bash
# Install UFW
sudo apt install -y ufw

# Default deny incoming
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (change port if needed)
sudo ufw allow 22/tcp

# Allow web UI (local network only)
sudo ufw allow from 192.168.0.0/16 to any port 5000

# Allow Modbus (if controller is remote)
sudo ufw allow out 502/tcp

# Enable firewall
sudo ufw enable
```

---

## 4. VPN/Tailscale Setup

Tailscale provides secure remote access without port forwarding.

### Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=<your-auth-key> --hostname=pool-pi-<location>
```

### Auto-Start on Boot

```bash
sudo systemctl enable tailscaled
```

### Access Remotely

Once connected, access the Pi via its Tailscale IP (100.x.x.x) from any device on your Tailscale network.

---

## 5. Disable Unnecessary Services

```bash
# Disable Bluetooth
sudo systemctl disable bluetooth
sudo systemctl mask bluetooth

# Disable HDMI (saves power)
sudo /usr/bin/tvservice -o

# Disable WiFi if using Ethernet
# Add to /boot/config.txt:
dtoverlay=disable-wifi

# Disable audio
# Add to /boot/config.txt:
dtparam=audio=off
```

---

## 6. Automatic Security Updates

```bash
sudo apt install -y unattended-upgrades

# Configure for security updates only
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## 7. Restrict User Permissions

```bash
# Lock down poolaissistant user
sudo usermod -s /usr/sbin/nologin poolaissistant

# Or restrict to specific commands via sudoers
sudo visudo

# Add:
poolaissistant ALL=(root) NOPASSWD: /usr/bin/systemctl restart poolaissistant_*
poolaissistant ALL=(root) NOPASSWD: /sbin/reboot
```

---

## 8. Monitoring & Alerts

The watchdog service (`watchdog.py`) monitors:
- Disk space (warning at 80%, critical at 90%)
- Memory usage (warning at 85%)
- Service health (auto-restarts failed services)

Enable it:
```bash
sudo cp /opt/PoolAIssistant/app/scripts/watchdog.service /etc/systemd/system/
sudo cp /opt/PoolAIssistant/app/scripts/watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable watchdog.timer
sudo systemctl start watchdog.timer
```

---

## 9. Database Maintenance

Run weekly:
```bash
python3 /opt/PoolAIssistant/app/scripts/db_optimize.py
```

Add to cron:
```bash
0 2 * * 0 /usr/bin/python3 /opt/PoolAIssistant/app/scripts/db_optimize.py
```

---

## Quick Hardening Checklist

- [ ] SSH key auth only, password disabled
- [ ] Firewall enabled (UFW)
- [ ] Tailscale for remote access
- [ ] Read-only root filesystem
- [ ] Watchdog timer enabled
- [ ] Log rotation configured
- [ ] Settings backup to cloud enabled
- [ ] Automatic security updates
- [ ] Unnecessary services disabled
