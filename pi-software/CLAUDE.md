# PoolAIssistant Pi Software

**Current Version: 6.11.22** (released 2026-07-27)

## Live Pi fleet (2026-06-11)

| Host | IP | Role |
|---|---|---|
| `PoolAI-swanwood` | `10.0.30.247` (WiFi, DHCP) + `192.168.200.100` (eth0) | Production — Swanwood Spa pool monitoring |

> `tvcctv` (the former second unit at `10.0.30.131`) was decommissioned — confirmed gone 2026-06-11. Swanwood is the only live Pi.

Updates land at the next 03:00 `update_check.timer` cron, or instantly via Settings → Check for Updates / `sudo python3 /opt/PoolAIssistant/app/scripts/update_check.py --apply`.

**v6.11.22 (2026-07-27): WiFi-drop zombie service killed for real, External Storage hardened, LSI history unblocked, settings cleanup.**
- WiFi kept dropping — root cause was `poolaissistant_ap_manager.service`, the old auto-failover AP daemon the v6.11.2 changelog says was "removed". Its retirement (stop/disable/remove-unit) only lived in `install_services.sh`, which only runs at install time and never re-executes on an already-deployed Pi via the incremental update path — so the daemon kept running, self-restarting under `Restart=always`, racing NetworkManager for 20+ releases. Worse: `watchdog.py`'s critical-services list included it, so it was being actively `systemctl restart`-ed back to life every ~5 minutes, which is almost certainly why any earlier manual `systemctl stop` never stuck. Script + unit removed from the repo entirely; `watchdog.py` fixed; `update_check.py` gained a fleet-wide self-heal (same pattern as the retired `remote_sync` cleanup) so any other Pi fixes itself on next update. Fixed live on Swanwood 2026-07-27.
- The USB stick found plugged into Swanwood was mid-migration from the real, shipped "External Storage" feature (`usb_data_mount.sh` + Settings → System), which offloads the growing SQLite DB onto external storage. The Flask route ran the whole mount+copy pipeline **synchronously** with a 180s `subprocess.run` timeout; copying a 6+GB live database over USB2/NTFS blew straight through it, and because the timeout only kills the immediate child (not the `cp` it had spawned), the copy kept running orphaned in the background for ~30 more minutes and left a dangling symlink instead of completing the directory swap. No data was lost — the swap step never ran. Rewrote the script to stop `poolaissistant_logger`/`poolaissistant_ui` before copying, run detached with a JSON status file the UI polls for live progress, and verify copy integrity (`sqlite3 PRAGMA integrity_check` + size comparison) before discarding the SD-card original.
- LSI history had never worked in production: `lsi_from_values()` returns an `LSIResult` frozen dataclass, not a dict, so `main_ui.py`'s `lsi_result.get("lsi", 0)` / `.get("pH_saturation")` calls raised `AttributeError` on every single calculation — silently swallowed by a broad `except Exception`, so `lsi_readings` was never once written to, which is why the already-built LSI history chart always showed "No LSI readings found." Fixed the two-attribute bug, narrowed the except clause, and fixed a second bug in the same code path: `db/lsi_history.py` used bare `with sqlite3.connect()` (commits but never closes — the same leak class as the v6.11.15 WAL-bloat incident), now uses the shared `db/connection.py` `get_connection()` helper. New `pooldash_app/lsi_interpretation.py` adds a fully internalized (no Claude/Anthropic API call, by design) plain-English interpretation + corrective-action checklist per LSI band.
- Maintenance page rebuilt around LSI (now the top card on the page): six overlapping entry points (Quick Actions grid, TDS card, Custom Note card, and the v6.11.13 "Log Past Entry" card — a superset re-implementation of the other three plus a timestamp field) collapsed to two — the quick-tap grid for "log this now", plus one consolidated form (action + optional note/TDS + optional backdate toggle) for everything else.
- Settings cleanup: removed 3 dead/no-op routes (`update_backend_credentials` was a complete no-op — `persist.save()` always overwrote it from hardcoded `SYSTEM_URLS` — plus the orphaned `update_upload_interval` and the dead `advanced_settings` redirect). Fixed the `storage_max_mb` "500" fallback bug in **7** places (not the 4 originally found — including two live "Reset to defaults"/clamp code paths that could actively re-persist the dangerous pre-v6.11.19 value). Added a **Portal Sync** section surfacing `cloud_upload_last_status`/`last_error` in the UI for the first time — closing the exact blind spot that let the v6.11.20 incident run silently for 9 days. De-duplicated validation logic (reboot-time regex, RS485 device sanitize — the latter had **three** separate copies) into `persist.py` as the single authority.
- 14 new tests (`test_lsi_storage.py`, `test_lsi_interpretation.py`), all passing alongside the existing suite. Every changed module verified via real Linux import/Jinja-parse checks on Swanwood before deploy (dev environment is Windows, lacks `fcntl`). The largest remaining piece from this pass — extracting the ~60 `/settings/*`/`/system/*` routes into a dedicated blueprint package and eliminating the `app.config` mirroring — is deliberately deferred to its own follow-up, per this pass's own risk-ordering (highest-diff, needs full local click-through testing with no staging Pi available).

**v6.11.21 (2026-07-18): data retention actually runs + journald actually persistent.**
- The v6.11.19 retention timer fired nightly but `data_cleanup.py` was killed at `TimeoutStartSec=1800` **every run** (verified: `cleanup_state.json` never written) — `aggregate_to_hourly()` deleted each hour-group with a non-indexable `strftime(...)=?` WHERE, one full 14M-row scan per group. Rewritten set-based: whole-day slices (one GROUP BY into a temp table + one indexed range DELETE + one bulk INSERT per day), a 20-min wall-clock budget (`--budget-seconds`), and resume cursors in `cleanup_state.json`, so the multi-month backlog drains over a few nights during the cool 03:19 window. Days already past the 90d mark aggregate straight to daily (single pass). Uses/creates `idx_readings_ts_pool`. Tests: `tools/tests/test_data_retention.py`.
- Persistent journald root cause found: Raspberry Pi OS ships `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf` (`Storage=volatile`) and drop-ins apply in **lexical filename order across conf.d dirs**, so it silently beat our `10-poolai-persistent.conf` — that's why every freeze/reboot investigation since v6.11.17 had no logs. The drop-in is now `99-poolai-persistent.conf` (wins), written by `update_check.py`'s self-heal (which previously only checked `/var/log/journal` existed — always true, never effective) and by `kiosk_setup.sh` (which previously *forced* volatile). Fixed live on Swanwood 2026-07-18; verified journal survives on disk.

**v6.11.20 (2026-06-24): cloud uploads silently broken since 2026-06-15, now fixed (two stacked bugs).**
- `cloud_upload.py`'s `get_controller_status()` queried `readings WHERE host=? ORDER BY ts DESC LIMIT 1` — SQLite picked `idx_readings_host_label` over `idx_readings_host_ts` and fell back to a temp-btree sort of every row for that host (millions of rows), taking minutes per controller and blowing the service's 120s start timeout every single tick. Same root cause class as the v6.11.18 dashboard iowait fix, in a script that never got it. Now reads `device_meta.last_seen_ts` (PK lookup, ~0ms) instead.
- Once that client-side hang was fixed, every tick reached the server and immediately hit a second, independent bug dating to at least 2026-06-09: `get_active_alarms()` named an alarm by `bit_name` alone (e.g. "b0"), which collides when two different registers (e.g. `Status_DigitalInputs` and `Status_LimitContactStates`) both have an open bit 0 on the same pool — the server's `UNIQUE KEY (device_id, pool, alarm_source)` on `device_alarms_current` rejected the second row and 500'd the *entire* snapshot (readings included). Fixed by combining `source_label.bit_name` into a unique source string; `snapshot.php`'s insert into `device_alarms_current` also switched to `INSERT IGNORE` as defense-in-depth (matches the existing pattern for alarm closures), so one bad alarm payload can never 500 the whole snapshot again.
- Diagnosed live on Swanwood via SSH + a one-shot self-deleting PHP probe against `event_log` (same pattern as `deploy_update.php`) since the server has no SSH access. Hotfixed on Swanwood directly, then shipped through the normal `deploy.py --target admin-backend` + tarball update channel.

**v6.11.13 (2026-06-11): screen never sleeps + backdated maintenance + local-only switch.**
- Kiosk autostart kills swayidle, runs a `wlopm --on '*'` keep-awake loop, and wraps Chromium in `lwrespawn` (a crashed browser over the black swaybg looked exactly like a sleeping screen). `update_check.py` self-heals installed autostarts on update; Swanwood was also hotfixed live via SSH on 2026-06-11.
- Eco/Sleep Mode removed entirely (persist defaults, System-tab form, base.html overlay, remote-settable allowlist).
- Maintenance page gains a "Log Past Entry" card — backdate an action/TDS/note to any past date; future timestamps rejected. Tests in `tools/tests/test_maintenance_backdate.py`.
- New `cloud_enabled` master switch (Settings → System → Cloud Connection): when off, heartbeat/snapshot/chunk/device/remote sync all exit early and the unit is a standalone appliance. Software updates deliberately stay on.

> Swanwood was on a static WiFi IP (`10.0.30.5`) prior to the 2026-04-26 v6.11.4 ipv4.dns="" incident. During recovery, the user reverted to DHCP and the Pi grabbed its old lease (`10.0.30.247`). v6.11.5 ships the preflight + DNS fallback that prevents recurrence; v6.11.10 includes that fix. If Swanwood is later reconfigured back to static, update this table.

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
