# PoolAIssistant Pi Software

**Current Version: 6.8.9** (March 2026)

## Quick Reference

### Credentials
```
SSH Access (when enabled):
  Username: poolai
  Host: poolai@<pi-ip> or poolai@poolai.local
  Example: poolai@10.0.30.144
  SSH Password: 12345678
  Sudo: NOPASSWD configured (no password needed)

Server (Hostinger):
  Subdomain: poolaissistant.modprojects.co.uk
  FTP Host: ftp.modprojects.co.uk
  FTP User: u931726538.mbs
  FTP Pass: Henley2026!

  WARNING: FTP cannot directly access poolaissistant directory!
  FTP is chrooted to customer portal. Use PHP installer scripts instead.
  See web-portal/CLAUDE.md for correct deployment process.

  Actual server path for poolaissistant.modprojects.co.uk:
    /home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/

Database (MySQL on Hostinger):
  Host: localhost
  Name: u931726538_PoolAIssistant
  User: u931726538_mbs_modproject
  Pass: PoolAI2026!

Admin Panel:
  URL: https://poolaissistant.modprojects.co.uk/admin/

Web UI Settings Password: PoolAI

Permanent Server Credentials (hardcoded in persist.py):
  backend_url: https://poolaissistant.modprojects.co.uk
  bootstrap_secret: e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9
```

### Pi Paths
```
App:      /opt/PoolAIssistant/app/
Data:     /opt/PoolAIssistant/data/
Settings: /opt/PoolAIssistant/data/pooldash_settings.json
Updates:  /opt/PoolAIssistant/data/updates/
VERSION:  /opt/PoolAIssistant/app/VERSION
```

### Services
```bash
sudo systemctl status poolaissistant_ui      # Flask web UI (port 8080)
sudo systemctl status poolaissistant_logger  # Modbus data logger
sudo systemctl restart poolaissistant_ui     # Restart web UI
```

---

## Software Update Process

### Creating & Deploying an Update

**IMPORTANT:** FTP cannot directly access the poolaissistant directory due to chroot.
Use this two-step process: upload to FTP, then use PHP installer to copy.

```powershell
# 1. Update VERSION file
echo "6.4.0" > VERSION

# 2. Create tarball (from PoolDash_v6 directory)
tar -czvf ../update-v6.4.0.tar.gz --exclude="__pycache__" --exclude="*.pyc" --exclude="instance" --exclude=".git" --exclude="*.sqlite3" --exclude="docs" .

# 3. Get checksum and size (Windows PowerShell)
certutil -hashfile ../update-v6.4.0.tar.gz SHA256
(Get-Item ../update-v6.4.0.tar.gz).Length

# 4. Upload tarball to FTP root (customer portal - where FTP has access)
curl --ftp-ssl -k -T ../update-v6.4.0.tar.gz -u "u931726538.mbs:Henley2026!" "ftp://ftp.modprojects.co.uk/"

# 5. Create deploy script (deploy_update.php) - see template below
# 6. Upload deploy script to FTP root
curl --ftp-ssl -k -T deploy_update.php -u "u931726538.mbs:Henley2026!" "ftp://ftp.modprojects.co.uk/"

# 7. Run deploy script via browser or curl
curl -s "https://poolai.modprojects.co.uk/deploy_update.php"
```

### deploy_update.php Template
```php
<?php
$version = '6.4.0';
$checksum = 'YOUR_SHA256_CHECKSUM';
$description = 'Update description here';
$filename = "update-v{$version}.tar.gz";

$src = __DIR__ . '/' . $filename;
$dest_dir = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/data/updates/';
$dest = $dest_dir . $filename;

if (!file_exists($src)) { die("Source not found: $src"); }
if (!is_dir($dest_dir)) { mkdir($dest_dir, 0755, true); }

if (copy($src, $dest)) {
    echo "Copied to $dest (" . filesize($dest) . " bytes)\n";

    require_once '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/config/database.php';
    $pdo = db();
    $stmt = $pdo->prepare("INSERT INTO software_updates (version, filename, file_size, checksum, description, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, NOW()) ON DUPLICATE KEY UPDATE file_size=VALUES(file_size), checksum=VALUES(checksum), is_active=1");
    $stmt->execute([$version, $filename, filesize($dest), $checksum, $description]);
    echo "Database updated\n";

    unlink($src);  // Clean up tarball from FTP root
    unlink(__FILE__);  // Self-delete installer
    echo "Done!\n";
} else {
    echo "Copy failed\n";
}
```

### Pi Update Methods
1. **Auto-update**: Runs daily at 3 AM via `update_check.timer`
2. **Manual via Web UI**: Settings → Check for Updates → Apply
3. **Manual via SSH**: `sudo python3 /opt/PoolAIssistant/app/scripts/update_check.py --apply`

---

## Clone Prep & Deployment

### Preparing a Pi for SD Card Cloning
```bash
# Run clone prep (stops services, clears data, removes SSH keys)
sudo /opt/PoolAIssistant/app/deploy/clone_prep.sh

# Then shutdown and clone the SD card
sudo shutdown -h now
```

### What Clone Prep Does
1. Stops all PoolAIssistant services
2. Deletes databases (pool_readings, maintenance_logs, alarm_log)
3. Resets settings to template (controllers cleared, device_id cleared)
4. Creates FIRST_BOOT marker
5. Cleans logs and bash history
6. Removes SSH host keys (regenerated on boot)
7. Resets machine-id

### What Survives Clone Prep (Permanent)
- `backend_url` and `bootstrap_secret` (hardcoded in persist.py DEFAULTS)
- Application code and scripts
- Service configurations

### After Cloning to New Pi
1. Pi boots with services enabled
2. SSH keys regenerate automatically
3. New device_id generated automatically
4. Auto-provisioning runs → gets new API key from server
5. Enable SSH via web UI (works without reboot now)

---

## Key Features (v6.4.0)

### SSH Enable Without Reboot
- SSH can be enabled via web UI and works immediately
- Generates host keys if missing, then starts service
- No reboot required after clone prep

### Instant Screen Rotation
- Screen rotation applies immediately via wlr-randr (Wayland)
- Settings: 0° (Normal), 90° (Counter-clockwise), 180° (Upside Down), 270° (Clockwise)
- Touchscreen calibration may need reboot

### Controller Proxy
- Access controller web UIs through the Pi from any network
- URL: `/proxy/ui/?host=<controller-ip>`
- Session-based host persistence for CSS/JS requests
- "Back to PoolAIssistant" button included

### Touch Scroll Buttons
- Scroll buttons appear when content is scrollable
- Works in Chromium kiosk mode on Pi touchscreen

---

## Project Structure

```
PoolDash_v6/
├── VERSION                    # Version number (read by Flask)
├── pooldash_app/              # Flask web application
│   ├── __init__.py            # App factory, version reading
│   ├── blueprints/
│   │   ├── main_ui.py         # Main routes, settings, SSH, rotation
│   │   ├── proxy.py           # Controller web UI proxy
│   │   ├── charts.py          # Plotly charts
│   │   └── alarms.py          # Alarm management
│   ├── templates/             # Jinja2 HTML templates
│   │   ├── base.html          # Main layout, scroll buttons, alarm banner
│   │   ├── pool.html          # Pool page with controller IP box
│   │   └── settings.html      # Settings page
│   ├── static/css/touch.css   # Touch-friendly CSS
│   └── persist.py             # Settings management (PERMANENT DEFAULTS HERE)
├── scripts/
│   ├── auto_provision.py      # Auto-register with server on boot
│   ├── update_check.py        # Software update checker/applier
│   ├── set_screen_rotation.sh # Apply screen rotation
│   └── systemd/               # Service unit files
└── deploy/
    ├── clone_prep.sh          # Prepare for SD card cloning
    └── first_boot_setup.sh    # First boot configuration
```

---

## Common Issues & Fixes

### SSH Connection Refused After Clone Prep
Enable SSH via web UI - it now works without reboot. The enable function:
1. Runs `ssh-keygen -A` to generate keys
2. Stops, enables, and starts SSH service
3. Verifies SSH is running

### Screen Rotation Not Applying
- Rotation applies instantly via Wayland (wlr-randr)
- If not working, check `wlr-randr` is installed
- Touch calibration needs reboot

### Controller Proxy Shows "No target host"
- Ensure URL includes `?host=<ip>`: `/proxy/ui/?host=192.168.200.11`
- Session stores host for subsequent CSS/JS requests

### Version Shows Wrong Number
```bash
sudo systemctl restart poolaissistant_ui
```

### Flask Not Starting
```bash
sudo journalctl -u poolaissistant_ui -n 50
```

---

## Key Configuration

### persist.py DEFAULTS (Permanent Values)
```python
"backend_url": "https://poolaissistant.modprojects.co.uk"
"bootstrap_secret": "e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9"
```
These are hardcoded and always used - they survive clone prep and cannot be overwritten by settings file.

### Settings Password
Protected settings in web UI require password: `PoolAI`

---

## Related Projects
- **Server code**: `../web-portal/` (has its own CLAUDE.md)
- **GitHub**: https://github.com/bensalmon91-cpu/poolaissistant-.git
