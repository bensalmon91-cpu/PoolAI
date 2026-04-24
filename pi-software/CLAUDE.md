# PoolAIssistant Pi Software

**Current Version: 6.11.4** (2026-04-24)

## Live Pi fleet (2026-04-24)

| Host | IP | Role |
|---|---|---|
| `PoolAI-swanwood` | `10.0.30.5` (WiFi, **static**) + `192.168.200.100` (eth0) | Production — Swanwood Spa pool monitoring |
| `tvcctv`          | `10.0.30.131` (WiFi, DHCP) + `192.168.200.101` (eth0)    | Second unit, full install, reaches the same pool controllers |

Both on **v6.11.4**. Both running the new manual-AP / health-watchdog / tabbed-settings stack from the 6.11.2–6.11.4 work.

## Quick Reference

### Credentials
```
SSH Access (when enabled):
  Username: poolai
  Host: poolai@<pi-ip> or poolai@poolai.local
  Examples:
    poolai@10.0.30.5     (Swanwood, production — pinned static IP)
    poolai@10.0.30.131   (tvcctv, DHCP)
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
sudo systemctl status poolaissistant_ui                # Flask web UI (port 80)
sudo systemctl status poolaissistant_logger            # Modbus data logger
sudo systemctl status poolaissistant_health_watchdog   # Reboots Pi if stuck >10 min
sudo systemctl restart poolaissistant_ui               # Restart web UI

# Manual AP toggle (v6.11.2+) — also wired to the UI:
sudo /usr/local/bin/ap_control.sh {start|stop|status}
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

## Key Features — current (v6.11.x)

### Tabbed Settings page (v6.11.2+)
Single `/settings` page split into 4 tabs: **Connectivity / Controllers / Maintenance / System**. Tab state persists in localStorage and also reads `?tab=` from the URL. On each card tap, scroll resets to top (friendly on the 800×480 touchscreen).

### Manual setup-mode AP (v6.11.2+)
No more auto-failover daemon that raced with NetworkManager. AP starts ONLY when the user taps "Turn On" in Settings → Connectivity, or during the first-boot oneshot if the clone has no WiFi and no ethernet. `ap_control.sh {start|stop|status}` is the single-source-of-truth CLI, with proper `192.168.4.1` cleanup on stop (the old daemon forgot this, leaving a ghost address that poisoned the IP display).

### Health watchdog (v6.11.2+)
`poolaissistant_health_watchdog.service` replaces the old AP manager. Every 60s, checks the default-route gateway; after 10 consecutive fails it reboots the Pi. Respects ethernet-only deployments (eth0 carrier + IP = healthy even without a default route) and refuses to trigger more than 3 reboots per hour.

### WiFi static IP via UI (v6.11.4)
Settings → Connectivity → WiFi card → **WiFi IP Configuration** (collapsible). Set wlan0 to DHCP or a static IP+gateway+netmask. Backend writes to the active WiFi NetworkManager profile (not the interface), so the setting persists across reboots and re-associations. Same pattern as the existing Ethernet static-IP flow.

### Install-time standard (v6.11.3)
Fresh installs now come up working without manual intervention: `setup_pi.sh` creates the `poolai` user, creates `/opt/PoolAIssistant/venv`, configures eth0 via NetworkManager on the pool subnet (default `192.168.200.100/24`), adds the hostname to `/etc/hosts`, and `install_services.sh` auto-starts the UI at the end. `.gitattributes` enforces LF line endings so shell scripts no longer silently break on line 2.

### Per-heartbeat network health (v6.11.2)
Pi uploads WiFi signal / regdom / disconnect-count metrics alongside each heartbeat; portal admin pages render a "Network" card with "Regdom conflict" / "Flappy" badges. Adds `device_health.network_json` column via idempotent migration.

### SSH enable without reboot
SSH can be enabled via web UI and works immediately (`ssh-keygen -A` + systemctl start ssh).

### Instant screen rotation
Rotation applies immediately via wlr-randr (Wayland). Touchscreen calibration still needs reboot.

### Controller proxy
Access controller web UIs through the Pi: `/proxy/ui/?host=<controller-ip>`. Session-based host persistence for subresource requests. "Back to PoolAIssistant" button.

### Touch scroll buttons
Scroll buttons appear when content overflows (Chromium kiosk mode on the touchscreen).

---

## Fresh SD Card Install Plan — v6.11.4

**Context:** v6.11.3 shipped a suite of install-time fixes to make fresh installs work end-to-end without manual intervention. All the fixes are in git and shipped to the release tarball, but **they have not yet been exercised on a clean Pi** — the two existing Pis (Swanwood, tvcctv) are both past install. The next fresh SD card flash is the validation moment. This plan is what to run and what to check.

### Prerequisites
- Blank microSD card (32 GB+ recommended)
- Raspberry Pi OS flashed (Debian trixie 64-bit, matches production)
- Touchscreen attached for recovery if anything goes wrong
- Ethernet cable plugged into the pool controller subnet (192.168.200.x)
- Home WiFi credentials (SSID + password) available

### Two install paths

**Path A — cloning from Swanwood (fastest, recommended):** Run `clone_prep.sh` on Swanwood, shutdown, clone the SD. New Pi boots with v6.11.4 code in place and the FIRST_BOOT marker triggers first-boot AP if no network.

**Path B — fresh OS flash:** Drop the v6.11.4 tarball onto a fresh Raspberry Pi OS install at `/opt/PoolAIssistant/app/`, then run the install scripts in order:
```bash
cd /opt/PoolAIssistant/app
sudo bash scripts/setup_pi.sh             # user, venv, eth0 static IP, hostname
sudo bash scripts/ensure_dependencies.sh  # apt packages, sudoers, symlinks
sudo bash scripts/install_services.sh     # timers + starts UI
```
For a unit that's not the first on the pool subnet, override the default eth0 IP:
```bash
sudo POOLAI_ETH_IP=192.168.200.102/24 bash scripts/setup_pi.sh
```

### Post-install verification checklist

- [ ] `cat /opt/PoolAIssistant/app/VERSION` → `6.11.4`
- [ ] `systemctl is-active poolaissistant_ui poolaissistant_logger poolaissistant_health_watchdog` → all `active`
- [ ] `id poolai` returns the service user with sudo group membership
- [ ] `/opt/PoolAIssistant/venv/bin/python --version` runs (venv created)
- [ ] `ip -4 -o addr show eth0` shows the pool-subnet static IP (192.168.200.x)
- [ ] `ping -c 2 192.168.200.11` succeeds (controllers reachable)
- [ ] `sudo -n true` as poolai succeeds (NOPASSWD configured)
- [ ] No `unable to resolve host …` warnings from sudo (hostname in `/etc/hosts`)
- [ ] `curl -sS http://localhost/settings | grep -c 'data-tab='` returns 4 (all tabs present)
- [ ] Browser at `http://<ip>/settings` renders the tab UI, Connectivity summary card shows correct IPs
- [ ] Settings → Controllers panel loads a pool controller list (or empty, pre-config)
- [ ] Settings → Connectivity → WiFi IP Configuration form renders and pre-fills current config
- [ ] Tap AP "Turn On" → wlan0 switches to `192.168.4.1` only (no 10.0.30.x); tap "Turn Off" → wlan0 returns to home WiFi with NO ghost `192.168.4.1`
- [ ] After 60s+ of uptime, `sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3 'SELECT COUNT(*) FROM readings'` > 0
- [ ] Reboot the Pi. After it comes back: all of the above still pass, VERSION still 6.11.4, static IPs survive.

### Symptoms-to-cause cheat sheet (for recovery)

| Symptom | Likely cause | Fix |
|---|---|---|
| Shell scripts fail on line 2 with "pipefail: invalid option name" | CRLF line endings snuck in | `find /opt/PoolAIssistant/app -name '*.sh' -exec sed -i 's/\r$//' {} \;` then retry. `.gitattributes` prevents this for future clones. |
| Flask service restart-loops at boot | `/opt/PoolAIssistant/venv` missing | `sudo -u poolai python3 -m venv /opt/PoolAIssistant/venv && sudo -u poolai /opt/PoolAIssistant/venv/bin/pip install -r /opt/PoolAIssistant/app/requirements.txt` |
| `journalctl -u poolaissistant_ui` → "User poolai does not exist" | poolai user wasn't created | Rerun `sudo bash /opt/PoolAIssistant/app/scripts/setup_pi.sh` |
| Logger spams "host unreachable" in logs | eth0 not on pool subnet | `sudo nmcli con show PoolAI-Ethernet` — if missing/wrong, rerun `setup_pi.sh` or manually create the profile |
| Sudo emits "unable to resolve host ..." warnings | hostname missing from `/etc/hosts` | `echo "127.0.1.1 $(hostname)" | sudo tee -a /etc/hosts` |
| Setup mode stuck on (ghost 192.168.4.1 on wlan0) | Stop command forgot cleanup (old bug) | `sudo ip addr del 192.168.4.1/24 dev wlan0` — and ensure `ap_control.sh` is v6.11.2+ |
| UI shows wrong IP (eth0 pool subnet, or stale DHCP) | `_primary_device_ip()` fallback needed updating, or cache stale | Wait 10s for cache TTL, or `systemctl restart poolaissistant_ui` |

### Reference material
- Previous deploy playbook (network redesign): `~/.claude/projects/.../memory/project_network_redesign_deploy.md`
- Installer improvement history / remaining backlog: same directory, `project_installer_improvements.md`
- Original design plan: `~/.claude/plans/sharded-crafting-hoare.md`

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
