# PoolAIssistant Pi Software

**Current Version: 6.8.8** (March 2026)

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
  FTP Root: /public_html/poolaissistant/

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
sudo systemctl status poolaissistant_ui      # Flask web UI (port 80)
sudo systemctl status poolaissistant_logger  # Modbus data logger
sudo systemctl restart poolaissistant_ui     # Restart web UI
```

---

## Software Update Process

### Creating & Deploying an Update

```powershell
# 1. Update VERSION file
echo "6.4.0" > VERSION

# 2. Create tarball (from PoolDash_v6 directory)
tar -czvf ../update-v6.4.0.tar.gz --exclude="__pycache__" --exclude="*.pyc" --exclude="instance" --exclude=".git" --exclude="*.sqlite3" --exclude="docs" .

# 3. Get checksum and size (Windows)
certutil -hashfile ../update-v6.4.0.tar.gz SHA256
wc -c < ../update-v6.4.0.tar.gz

# 4. Upload via FTP
curl --ftp-ssl -T ../update-v6.4.0.tar.gz -u "u931726538.mbs:Henley2026!" "ftp://ftp.modprojects.co.uk/poolaissistant/data/updates/"

# 5. Add to database via PHP script:
cat > /tmp/add.php << 'EOF'
<?php
require_once __DIR__ . '/../config/database.php';
$pdo = db();
$stmt = $pdo->prepare("INSERT INTO software_updates (version, filename, file_size, checksum, description, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, NOW())");
$stmt->execute(['6.4.0', 'update-v6.4.0.tar.gz', FILE_SIZE, 'CHECKSUM', 'Description']);
echo "Added";
EOF
curl -T /tmp/add.php -u "u931726538.claudeaccess:BQWZ&4GC@dFx&Q1o" "ftp://ftp.modprojects.co.uk/api/add_update.php"
curl -s "https://poolaissistant.modprojects.co.uk/api/add_update.php"
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

### 502 Bad Gateway nginx Error
**Cause**: Old Pi images had nginx proxying to Flask. Current software runs Flask directly on port 80 (no nginx), but nginx wasn't removed during update.

**Fix via SSH** (if SSH is enabled):
```bash
sudo systemctl stop nginx
sudo apt-get remove -y --purge nginx nginx-common
sudo apt-get autoremove -y
sudo systemctl restart poolaissistant_ui
```

**If SSH not available**: Flash a new SD card image or manually access the Pi with keyboard/monitor.

**Prevention**: Updates from v6.7.8+ automatically remove nginx.

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

## Pending Fixes (v6.8.9 TODO)

### Priority 1: Critical (System Stability)

#### Read-Only Filesystem Errors (Issues 11 & 14)
- **Problem**: `scripts/update_wifi.sh` writes to `/etc/NetworkManager/system-connections/` which fails on read-only Pi filesystem
- **Cause**: Pi uses read-only root filesystem for SD card protection
- **Fix**: Add remount functions to `update_wifi.sh`:
  ```bash
  remount_rw() { mount | grep -q "on / type.*ro," && mount -o remount,rw / || true; }
  remount_ro() { mount | grep -q "on / type.*rw" && mount -o remount,ro / || true; }
  trap remount_ro EXIT
  remount_rw
  ```
- **Status**: [ ] Not started

#### AP Mode Not Starting When No WiFi (Issue 15)
- **Problem**: AP mode doesn't default to on when WiFi is not connected
- **File**: `scripts/poolaissistant_ap_manager.sh`
- **Fix**: Add 5-second delay at startup for interfaces to initialize (~line 453)
- **Status**: [ ] Not started

### Priority 2: High (Blocking Workflows)

#### No Way to Bypass WiFi Wizard If No Networks (Issue 4)
- **Problem**: When no networks found, user has no obvious way to continue
- **File**: `pooldash_app/templates/setup_wizard.html` (~line 1256)
- **Fix**: Show prominent "Continue Without WiFi" button and "Scan Again" button
- **Status**: [ ] Not started

#### No Back Button in IP Viewer/Proxy Errors (Issue 7)
- **Problem**: Users get stuck when proxy errors occur
- **File**: `pooldash_app/blueprints/proxy.py` (lines 32, 44-45)
- **Fix**: Add back button HTML to all error responses
- **Status**: [ ] Not started

#### Plotly CDN Failures Break Charts (Issue 9)
- **Problem**: Charts fail when CDN is unreachable
- **Files**: `pooldash_app/blueprints/charts.py`, `pooldash_app/static/js/`
- **Fix**: Add `onerror` fallback to local Plotly copy, download `plotly-basic-2.27.0.min.js`
- **Status**: [ ] Not started

#### No Loading Indicator for WiFi Connecting (Issue 12)
- **Problem**: `connectWifi()` provides no feedback during connection
- **Files**: `pooldash_app/templates/setup_wizard.html`, `pooldash_app/blueprints/main_ui.py`
- **Fix**: Show "Connecting..." state, add `/setup/connect-wifi` endpoint
- **Status**: [ ] Not started

### Priority 3: Medium (UX Improvements)

#### Screen Rotation Not Applying During Wizard (Issue 1)
- **Files**: `setup_wizard.html`, `main_ui.py`
- **Fix**: Add AJAX call in `selectRotation()`, add `/setup/apply-rotation` endpoint
- **Status**: [ ] Not started

#### WiFi List Shows Max 4 Networks (Issue 2)
- **File**: `setup_wizard.html` (~line 395)
- **Fix**: Increase `.wifi-list` max-height from 250px to 400px
- **Status**: [ ] Not started

#### Popup Keyboard Too Small (Issue 3)
- **File**: `setup_wizard.html` (~lines 1714-1746)
- **Fix**: Increase button sizes (min-width: 36px, height: 48px, max-width: 48px)
- **Status**: [ ] Not started

#### Auto-Focus IP Input After Adding Controller (Issue 5)
- **File**: `setup_wizard.html` (~line 1558)
- **Fix**: Add `.focus()` call after clearing input
- **Status**: [ ] Not started

#### No Way to Edit/Delete Controller IP in Wizard (Issue 6)
- **File**: `setup_wizard.html` (~line 1511)
- **Fix**: Change IP from `<span>` to `<input>`, add delete button, add JS functions
- **Status**: [ ] Not started

#### Wizard Needs IP Address Configuration Step (Issue 8)
- **File**: `setup_wizard.html`
- **Fix**: Add new step between WiFi and Storage for ethernet IP setup
- **Status**: [ ] Not started

#### Auto-Scan WiFi on "Change Network" Expand (Issue 10)
- **File**: `pooldash_app/templates/settings.html` (~line 461)
- **Fix**: Add event listener on details toggle to trigger `scanWifi()`
- **Status**: [ ] Not started

#### Protected Settings Scroll Issue (Issue 13)
- **File**: `pooldash_app/templates/system.html` (~line 605)
- **Fix**: Add `scrollIntoView()` call after unlocking protected settings
- **Status**: [ ] Not started

---

## Related Projects
- **Server code**: `../../web-portal/` (has its own CLAUDE.md)
- **GitHub**: https://github.com/bensalmon91-cpu/poolaissistant-.git
