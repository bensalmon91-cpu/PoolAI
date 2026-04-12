# PoolAIssistant Universal Deployment Guide

Version 6.1.1 - Universal Multi-Site Deployment

## Table of Contents

1. [Overview](#overview)
2. [Pre-Deployment Planning](#pre-deployment-planning)
3. [Creating a Master Image](#creating-a-master-image)
4. [Deployment Workflows](#deployment-workflows)
5. [Network Configuration](#network-configuration)
6. [Troubleshooting](#troubleshooting)
7. [Appendix](#appendix)

---

## Overview

PoolAIssistant v6.1.1 is designed for universal deployment across multiple sites with different network configurations. The system uses externalized configuration files, allowing a single master image to be cloned and deployed to any network environment.

### Key Features

- **Network Universal**: Works on any subnet (192.168.x.x, 10.0.x.x, etc.)
- **Multi-Controller Support**: Up to 10 controllers per site
- **Flexible Deployment**: Interactive setup or pre-configured
- **Modbus Profiles**: Supports Ezetrol, Bayrol, and Dulcopool controllers
- **Settings Externalized**: All network-specific settings in JSON files

### Deployment Methods

1. **Interactive Setup**: Boot cloned SD card and run configuration wizard
2. **Pre-Configuration**: Configure SD card before shipping to site
3. **Remote Configuration**: Configure via SSH after deployment

---

## Pre-Deployment Planning

### Site Survey Checklist

Before deploying PoolAIssistant to a new site, gather the following information:

#### Network Information
- [ ] Network subnet (e.g., 192.168.1.x, 10.0.0.x)
- [ ] Available static IP for Pi (or DHCP acceptable)
- [ ] Gateway IP
- [ ] DNS servers (if required)
- [ ] WiFi credentials (if using WiFi instead of Ethernet)

#### Controller Information

For each pool controller:

- [ ] Controller IP address
- [ ] Controller port (usually 502)
- [ ] Controller type (Ezetrol, Bayrol, Dulcopool)
- [ ] Controller name/label (e.g., "Main Pool", "Spa")
- [ ] Pool volume in liters (optional)
- [ ] Special configuration notes

#### Access Requirements
- [ ] On-site personnel contact information
- [ ] Remote access method (VPN, port forwarding, etc.)
- [ ] Fallback access plan (AP mode SSID: PoolAIssistant-AP)

### Site Survey Template

Create a file: `site_<name>.json`

```json
{
  "site_name": "Riverside Pool Complex",
  "deployment_date": "2026-02-15",
  "contact_name": "John Smith",
  "contact_phone": "+1-555-0100",
  "network": {
    "subnet": "192.168.50.0/24",
    "pi_ip": "192.168.50.100",
    "gateway": "192.168.50.1",
    "dns": "8.8.8.8"
  },
  "controllers": [
    {
      "enabled": true,
      "host": "192.168.50.10",
      "name": "Main Pool",
      "port": 502,
      "volume_l": 80000,
      "notes": "25m indoor pool"
    },
    {
      "enabled": true,
      "host": "192.168.50.11",
      "name": "Spa",
      "port": 502,
      "volume_l": 5000,
      "notes": "Outdoor spa, 8-person"
    }
  ],
  "modbus_profile": "ezetrol",
  "ezetrol_layout": "CDAB"
}
```

---

## Creating a Master Image

### Prerequisites

- A working PoolAIssistant Pi installation (current: 10.0.30.80)
- SD card reader for PC
- Sufficient disk space for image (~8-16GB)
- DD or Win32DiskImager for imaging

### Step 1: Prepare Current Pi for Cloning

SSH to the Pi:

```bash
ssh poolaissitant@10.0.30.80
```

Upload and run the clone preparation script:

```bash
# On PC - upload script
scp clone_prep.sh poolaissitant@10.0.30.80:/tmp/

# On Pi - run script
ssh poolaissitant@10.0.30.80
sudo bash /tmp/clone_prep.sh
```

The script will:
- Stop all services
- Backup and clear databases (2.4GB freed)
- Create template settings
- Clean logs
- Remove SSH host keys (regenerate on first boot)
- Create first-boot marker

When complete, shut down:

```bash
sudo shutdown -h now
```

### Step 2: Create SD Card Image

#### On Linux/Mac:

```bash
# Insert SD card and find device
lsblk

# Create image (replace /dev/sdX with your SD card)
sudo dd if=/dev/sdX of=poolaissistant_v6.1.1_master.img bs=4M status=progress

# Compress to save space
gzip poolaissistant_v6.1.1_master.img
```

#### On Windows:

1. Use Win32DiskImager or similar tool
2. Select SD card drive
3. Choose output file: `poolaissistant_v6.1.1_master.img`
4. Click "Read"
5. Compress with 7-Zip or similar

### Step 3: Store Master Image

Store the master image securely:

```
images/
  poolaissistant_v6.1.1_master.img.gz
  poolaissistant_v6.1.1_master.md5
  README.txt
```

Generate checksum:

```bash
md5sum poolaissistant_v6.1.1_master.img.gz > poolaissistant_v6.1.1_master.md5
```

---

## Deployment Workflows

### Workflow 1: Interactive On-Site Setup

**Use when**: Technician is on-site and can access controllers

#### Steps:

1. **Flash SD Card**
   ```bash
   # Decompress image
   gunzip poolaissistant_v6.1.1_master.img.gz

   # Flash to SD card
   sudo dd if=poolaissistant_v6.1.1_master.img of=/dev/sdX bs=4M status=progress
   ```

2. **Insert and Boot**
   - Insert SD card into Pi
   - Connect Ethernet to site network
   - Power on Pi

3. **Find Pi IP Address**
   - Check router DHCP leases
   - Or use: `nmap -sn 192.168.x.0/24 | grep -i raspberry`
   - Or connect monitor/keyboard to see IP on boot

4. **SSH to Pi**
   ```bash
   ssh poolaissitant@<pi-ip>
   # Default password: (check with deployer)
   ```

5. **Run First-Boot Setup**
   ```bash
   cd /opt/PoolAIssistant/app
   sudo bash first_boot_setup.sh
   ```

6. **Follow Interactive Wizard**
   - Enter site name
   - Configure each controller (IP, name, port, volume)
   - Test connectivity to controllers
   - Select Modbus profile
   - Confirm settings

7. **Verify Installation**
   ```bash
   # Check services
   sudo systemctl status poolaissistant_logger
   sudo systemctl status poolaissistant_ui

   # Check logs
   journalctl -u poolaissistant_logger -n 50

   # Access web UI
   http://<pi-ip>:8080
   ```

### Workflow 2: Pre-Configuration Before Shipping

**Use when**: Site network details are known in advance

#### Steps:

1. **Create Site Configuration**

   Create file: `configs/site_abc.json`

   ```json
   {
     "controllers": [
       {
         "enabled": true,
         "host": "192.168.50.10",
         "name": "Main Pool",
         "port": 502,
         "volume_l": 80000
       }
     ],
     "modbus_profile": "ezetrol",
     "ezetrol_layout": "CDAB",
     "maintenance_actions": [
       "Backwash Filter 1",
       "Clean Chlorine Probe",
       "Clean pH Probe",
       "Add Chlorine",
       "Add pH Up",
       "Add pH Down",
       "Custom note"
     ]
   }
   ```

2. **Flash Master Image**
   ```bash
   sudo dd if=poolaissistant_v6.1.1_master.img of=/dev/sdX bs=4M status=progress
   ```

3. **Mount SD Card**
   ```bash
   # Wait for partitions to mount
   # Find ext4 partition (usually /dev/sdX2)
   sudo mount /dev/sdX2 /mnt/sd_card
   ```

4. **Pre-Configure SD Card**
   ```bash
   ./pre_configure.sh /mnt/sd_card configs/site_abc.json
   ```

5. **Unmount and Ship**
   ```bash
   sync
   sudo umount /mnt/sd_card
   ```

6. **On-Site Installation**
   - Insert SD card
   - Connect to network
   - Power on
   - Pi auto-configures and starts
   - Access at `http://<pi-ip>:8080`

### Workflow 3: Remote Configuration

**Use when**: Pi is deployed but needs reconfiguration

#### Steps:

1. **SSH to Pi**
   ```bash
   ssh poolaissitant@<pi-ip>
   ```

2. **Stop Services**
   ```bash
   sudo systemctl stop poolaissistant_logger poolaissistant_ui
   ```

3. **Edit Settings**
   ```bash
   sudo nano /opt/PoolAIssistant/data/pooldash_settings.json
   ```

4. **Restart Services**
   ```bash
   sudo systemctl start poolaissistant_logger poolaissistant_ui
   ```

5. **Verify**
   ```bash
   journalctl -u poolaissistant_logger -f
   ```

---

## Network Configuration

### Standard Configuration

By default, PoolAIssistant expects controllers to be reachable on the same network as the Pi.

**Example 1: Simple Flat Network**
```
Router (192.168.1.1)
  ├─ Pi (192.168.1.100)
  ├─ Controller 1 (192.168.1.10)
  └─ Controller 2 (192.168.1.11)
```

**Example 2: Subnet with Static IP**
```
Gateway (10.0.30.1)
  ├─ Pi (10.0.30.80)
  └─ Controllers (192.168.200.11-14)
```

### Access Point Fallback Mode

If the Pi cannot reach controllers or loses network connectivity, it automatically creates an access point:

- **SSID**: `PoolAIssistant-AP`
- **Password**: Check `/etc/PoolAIssistant/poolaissistant.env`
- **Pi IP**: `192.168.2.1`
- **Web UI**: `http://192.168.2.1:8080`

Connect to this AP to reconfigure network settings.

### VPN Access (Optional)

For remote monitoring, configure VPN on the Pi:

```bash
# Install WireGuard or OpenVPN
sudo apt install wireguard

# Configure tunnel
sudo nano /etc/wireguard/wg0.conf

# Enable on boot
sudo systemctl enable wg-quick@wg0
```

---

## Troubleshooting

### Pi Not Booting

**Symptoms**: No HDMI output, no network activity

**Solutions**:
1. Check power supply (requires 5V 3A minimum)
2. Check SD card is properly inserted
3. Re-flash SD card
4. Try different SD card (corrupted card)

### Cannot Access Web UI

**Symptoms**: Cannot reach `http://<pi-ip>:8080`

**Solutions**:

1. **Check Pi is on network**
   ```bash
   ping <pi-ip>
   ```

2. **Check web UI service**
   ```bash
   ssh poolaissitant@<pi-ip>
   sudo systemctl status poolaissistant_ui
   ```

3. **Check firewall**
   ```bash
   sudo ufw status
   # If blocking, allow port 8080
   sudo ufw allow 8080/tcp
   ```

4. **Access via AP mode**
   - Connect to `PoolAIssistant-AP` WiFi
   - Navigate to `http://192.168.2.1:8080`

### No Data From Controllers

**Symptoms**: Web UI shows "No data" or old data

**Solutions**:

1. **Check logger service**
   ```bash
   sudo systemctl status poolaissistant_logger
   journalctl -u poolaissistant_logger -n 50
   ```

2. **Test controller connectivity**
   ```bash
   cd /opt/PoolAIssistant/app
   source /opt/PoolAIssistant/venv/bin/activate
   python3 test_modbus_connection.py --host 192.168.1.10 --port 502
   ```

3. **Verify network routing**
   ```bash
   ping 192.168.1.10
   traceroute 192.168.1.10
   ```

4. **Check controller configuration**
   ```bash
   cat /opt/PoolAIssistant/data/pooldash_settings.json
   ```

### Database Issues

**Symptoms**: Errors about locked database, corrupt data

**Solutions**:

1. **Check database integrity**
   ```bash
   sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3 "PRAGMA integrity_check;"
   ```

2. **Stop services and repair**
   ```bash
   sudo systemctl stop poolaissistant_logger poolaissistant_ui
   sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3 "VACUUM;"
   sudo systemctl start poolaissistant_logger poolaissistant_ui
   ```

3. **Backup and reset database**
   ```bash
   sudo systemctl stop poolaissistant_logger poolaissistant_ui
   sudo mv /opt/PoolAIssistant/data/pool_readings.sqlite3 /tmp/pool_readings.backup
   cd /opt/PoolAIssistant/app
   source /opt/PoolAIssistant/venv/bin/activate
   python3 -c "from modbus_logger import init_db; init_db()"
   sudo systemctl start poolaissistant_logger poolaissistant_ui
   ```

### Alarm Page Errors

**Symptoms**: Alarms page shows errors or fails to load

**Solutions**:

1. **Check alarm_events table exists**
   ```bash
   sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3 ".tables"
   ```

2. **Check recent logs**
   ```bash
   journalctl -u poolaissistant_ui -n 100 | grep -i alarm
   ```

3. **Verify alarm endpoint**
   ```bash
   curl http://localhost:8080/alarms/api/Main
   ```

---

## Appendix

### File Locations

| Path | Purpose |
|------|---------|
| `/opt/PoolAIssistant/app/` | Application code |
| `/opt/PoolAIssistant/data/` | Databases and settings |
| `/opt/PoolAIssistant/data/pooldash_settings.json` | Controller configuration |
| `/opt/PoolAIssistant/data/pool_readings.sqlite3` | Sensor readings database |
| `/opt/PoolAIssistant/data/maintenance_logs.sqlite3` | Maintenance logs database |
| `/etc/PoolAIssistant/poolaissistant.env` | Environment variables |
| `/etc/systemd/system/poolaissistant_*.service` | Service definitions |

### Default Credentials

- **SSH User**: `poolaissitant`
- **SSH Password**: (Set during initial setup)
- **Web UI**: No authentication (internal network only)
- **AP Mode SSID**: `PoolAIssistant-AP`
- **AP Mode Password**: (Check `/etc/PoolAIssistant/poolaissistant.env`)

### Service Management

```bash
# Check status
sudo systemctl status poolaissistant_logger
sudo systemctl status poolaissistant_ui
sudo systemctl status poolaissistant_ap_manager

# Start services
sudo systemctl start poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager

# Stop services
sudo systemctl stop poolaissistant_logger poolaissistant_ui poolaissistant_ap_manager

# Restart services
sudo systemctl restart poolaissistant_logger poolaissistant_ui

# View logs
journalctl -u poolaissistant_logger -f
journalctl -u poolaissistant_ui -f
```

### Network Utilities

```bash
# Find Pi on network
nmap -sn 192.168.1.0/24

# Test Modbus connection
cd /opt/PoolAIssistant/app
source /opt/PoolAIssistant/venv/bin/activate
python3 test_modbus_connection.py --host 192.168.1.10 --port 502

# Check IP address
hostname -I

# Check network interfaces
ip addr show

# Check routing
ip route show
```

### Backup and Restore

**Backup Configuration:**
```bash
# On Pi
tar -czf ~/poolai_backup_$(date +%Y%m%d).tar.gz \
  /opt/PoolAIssistant/data/pooldash_settings.json \
  /etc/PoolAIssistant/poolaissistant.env

# Copy to PC
scp poolaissitant@<pi-ip>:~/poolai_backup_*.tar.gz .
```

**Backup Database:**
```bash
# On Pi
sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3 ".backup /tmp/pool_readings_backup.sqlite3"
scp /tmp/pool_readings_backup.sqlite3 user@pc:/backup/
```

**Restore Configuration:**
```bash
# Copy to Pi
scp poolai_backup_20260130.tar.gz poolaissitant@<pi-ip>:~/

# On Pi
cd /
sudo tar -xzf ~/poolai_backup_20260130.tar.gz
sudo systemctl restart poolaissistant_logger poolaissistant_ui
```

### Support Contacts

- **Developer**: (contact info)
- **Documentation**: `README.md`, `OPTIMIZATION_SUMMARY.md`
- **Source Code**: (repository link if applicable)

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 6.1.1 | 2026-01-30 | Universal deployment support, alarm system fix |
| 6.1.0 | 2026-01-15 | Multi-controller support, settings externalization |
| 6.0.0 | 2025-12-01 | Major rewrite, Flask UI, modular architecture |

---

**End of Deployment Guide**
