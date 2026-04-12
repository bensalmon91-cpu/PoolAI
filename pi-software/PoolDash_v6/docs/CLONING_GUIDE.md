# PoolAIssistant SD Card Cloning Guide

This guide explains how to clone a configured PoolAIssistant Pi to deploy at new sites.

## Overview

The auto-provisioning system allows cloned Pi devices to automatically register themselves with the MOD Projects server on first boot. Each Pi gets a unique device ID and API key without manual configuration.

## Prerequisites

- A fully configured "master" Pi with PoolAIssistant installed
- Bootstrap secret configured on both the server and Pi
- Network/WiFi configured for the target site (or use the AP manager)

## Before Cloning: Prepare the Master SD Card

Run this command on the Pi to clear device-specific settings:

```bash
sudo systemctl stop poolaissistant_ui
python3 -c "
import json
settings_path = '/opt/PoolAIssistant/data/pooldash_settings.json'
with open(settings_path, 'r') as f:
    data = json.load(f)

# Clear device-specific values (new ones generated on first boot)
data['device_id'] = ''
data['remote_api_key'] = ''
data['device_alias'] = ''
data['last_remote_sync_ts'] = ''

# Keep these configured:
# - backend_url (server address)
# - bootstrap_secret (for auto-provisioning)
# - controllers (Modbus settings - adjust per site if needed)
# - remote_sync_enabled (True)

with open(settings_path, 'w') as f:
    json.dump(data, f, indent=2, sort_keys=True)

print('Settings cleared for cloning!')
print('device_id, remote_api_key, device_alias cleared')
"
```

## Clone the SD Card

1. **Shut down the Pi cleanly:**
   ```bash
   sudo shutdown -h now
   ```

2. **Remove the SD card** and insert into your computer

3. **Create an image** using one of these tools:
   - **Windows**: Win32 Disk Imager, balenaEtcher
   - **macOS**: balenaEtcher, `dd` command
   - **Linux**: balenaEtcher, `dd` command

   Example with dd (Linux/macOS):
   ```bash
   sudo dd if=/dev/sdX of=poolaissistant_master.img bs=4M status=progress
   ```

4. **Write the image** to new SD cards for each deployment site

## First Boot at New Site

When the cloned Pi boots at a new site:

1. **Auto-provision service runs** (`auto_provision.service`)
2. **New device_id generated** (UUID)
3. **Pi contacts the server** with bootstrap_secret
4. **Server registers the device** and returns an API key
5. **Pi saves the API key** and enables sync
6. **Data sync begins** on the configured schedule

## Post-Deployment: Set Device Alias

After the Pi is running at the new site, set a friendly name:

**Option 1: Via Web UI**
1. Go to `http://<pi-ip>:8080/settings/advanced`
2. Enter the site name in "Device Alias"
3. Click Save

**Option 2: Via SSH**
```bash
python3 -c "
import json
settings_path = '/opt/PoolAIssistant/data/pooldash_settings.json'
with open(settings_path, 'r') as f:
    data = json.load(f)
data['device_alias'] = 'New Site Name Here'
with open(settings_path, 'w') as f:
    json.dump(data, f, indent=2, sort_keys=True)
print('Device alias updated!')
"
```

## Site-Specific Configuration

If the new site has different Modbus controllers, update after deployment:

1. Go to `http://<pi-ip>:8080/settings`
2. Configure the controller IP addresses and names
3. Save settings

## Verify Deployment

1. **Check admin dashboard**: https://poolaissistant.modprojects.co.uk/admin/
   - New device should appear under "Devices"

2. **Check Pi logs**:
   ```bash
   sudo journalctl -u auto_provision -n 50
   sudo journalctl -u poolaissistant_ui -n 50
   ```

3. **Test manual sync**:
   ```bash
   /opt/PoolAIssistant/venv/bin/python /opt/PoolAIssistant/app/scripts/remote_sync.py --force
   ```

## Troubleshooting

### Pi doesn't auto-register
- Check network connectivity
- Verify bootstrap_secret matches server setting
- Check logs: `sudo journalctl -u auto_provision`

### Device shows wrong name in dashboard
- Update device_alias in Pi settings
- Or rename in admin dashboard under Devices

### Sync not working
- Verify remote_sync_enabled is True
- Check remote_api_key is populated
- Check remote_sync_url is correct
- Test with: `python /opt/PoolAIssistant/app/scripts/remote_sync.py --force`

## Important Paths

| Item | Path |
|------|------|
| Settings | `/opt/PoolAIssistant/data/pooldash_settings.json` |
| Pool Database | `/opt/PoolAIssistant/data/pool_readings.sqlite3` |
| Scripts | `/opt/PoolAIssistant/app/scripts/` |
| Logs | `sudo journalctl -u poolaissistant_ui` |

## Services

| Service | Purpose |
|---------|---------|
| `poolaissistant_ui` | Main web interface |
| `auto_provision` | Registers device on boot |
| `remote_sync.timer` | Periodic data sync |
| `storage_monitor` | Monitors disk space |

Check service status:
```bash
sudo systemctl status poolaissistant_ui
sudo systemctl status auto_provision
sudo systemctl status remote_sync.timer
sudo systemctl status storage_monitor
```
