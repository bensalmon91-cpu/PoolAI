# PoolAIssistant Pi Software (PoolDash_v6 app)

**Current Version: 6.11.4** (2026-04-24)

> This file documents the Flask app inside `PoolDash_v6/`.
> For the higher-level install / fleet / deploy docs see the parent
> [`pi-software/CLAUDE.md`](../CLAUDE.md) — it has the fresh SD card install plan
> and the current live Pi inventory.

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

## Recently landed (v6.11.2 — v6.11.4)

See commits `58933ac`, `f75ce4d`, `5890b66` for details. Highlights:

- **Network redesign (v6.11.2)** — auto-failover AP daemon removed, replaced by manual `ap_control.sh` toggle + `health_watchdog.sh` reboot-if-stuck. Missing `192.168.4.1/24` cleanup on AP teardown fixed. `update_wifi.sh` now upserts by SSID (no more duplicate profile accumulation). Settings page reorganized into 4 tabs. `_primary_device_ip()` picks the default-route interface for display.
- **Installer cleanup (v6.11.3)** — fresh installs work end-to-end: `.gitattributes` forces LF on shell scripts, `setup_pi.sh` creates `poolai` user + venv + eth0 static IP on pool subnet, `install_services.sh` auto-starts UI, example env no longer ships placeholder pool IPs (logger falls back to `pooldash_settings.json`).
- **WiFi static IP UI (v6.11.4)** — Settings → Connectivity → WiFi IP Configuration. New `update_wifi_ip.sh` helper modifies the active WiFi NM profile, same pattern as Ethernet.
- **Read-only filesystem remount (v6.11.2)** — `update_wifi.sh` now does `remount_rw` / `remount_ro` around nmcli writes to `/etc/NetworkManager/system-connections/`. Addresses the old Issues 11 & 14.

## Known rough edges (post-install UX, deferred backlog)

Not blockers — the main flow works, these are the remaining papercuts. Each
lives in the setup wizard (runs on first boot of a fresh clone). Would be a
natural v6.11.5 or v6.12.0 polish pass after the fresh-install validation
proves the standard flow works end-to-end.

| # | File | Fix |
|---|---|---|
| Issue 1 | `setup_wizard.html`, `main_ui.py` | Screen rotation not applied live during wizard — needs AJAX call in `selectRotation()` + `/setup/apply-rotation` endpoint |
| Issue 2 | `setup_wizard.html` ~line 395 | WiFi list capped at max-height 250px, looks like only 4 networks — bump to 400px |
| Issue 3 | `setup_wizard.html` ~lines 1714-1746 | Popup keyboard buttons too small for touch — increase to min-width 36px / height 48px |
| Issue 4 | `setup_wizard.html` ~line 1256 | "No networks found" dead end — show a "Continue Without WiFi" + "Scan Again" button |
| Issue 5 | `setup_wizard.html` ~line 1558 | Auto-focus IP input after adding a controller |
| Issue 6 | `setup_wizard.html` ~line 1511 | Can't edit or delete a controller IP once added — change from span to input, add delete button |
| Issue 7 | `proxy.py` lines 32, 44-45 | Proxy error responses have no "Back" button — user gets stuck |
| Issue 8 | `setup_wizard.html` | Wizard could have an explicit Ethernet IP step (v6.11.4 UI covers this for post-install, wizard still lacks it) |
| Issue 9 | `charts.py`, `static/js/` | Plotly CDN unreachable breaks charts — add `onerror` fallback to local `plotly-basic-2.27.0.min.js` |
| Issue 12 | `setup_wizard.html`, `main_ui.py` | `connectWifi()` gives no "Connecting..." feedback — add loading state + `/setup/connect-wifi` |
| Issue 13 | `system.html` ~line 605 | After unlocking protected settings, no `scrollIntoView()` — user has to scroll |

Items shipped in v6.11.x: Issues 10 (auto-scan WiFi on "Change Network" toggle), 11 & 14 (RO-FS remount), 15 (AP mode auto-failover — obsoleted by the manual-AP redesign).

---

## Related Projects
- **Server code**: `../../web-portal/` (has its own CLAUDE.md)
- **GitHub**: https://github.com/bensalmon91-cpu/poolaissistant-.git
