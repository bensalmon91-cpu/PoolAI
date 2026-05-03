# PoolAIssistant Server (Web Portal)

**Topic: PoolAIssistant Backend Server - PHP/MySQL on Hostinger**

This is the server-side component that handles device provisioning, software updates, and data sync for PoolAIssistant Pi devices.

## Quick Reference

### Credentials
```
=== FTP ACCESS ===
  Host: ftp.modprojects.co.uk
  User: u931726538.mbs
  Pass: Henley2026!

  NOTE: FTP is chrooted to poolai.modprojects.co.uk; admin-domain deploys hop via PHP installer.
  See "Domain split" below for the full picture.

=== URLS ===
Admin backend: https://poolaissistant.modprojects.co.uk  (admin panel: /admin/)
Customer portal: https://poolai.modprojects.co.uk

=== SHARED DATABASE (MySQL) ===
Host: localhost
Name: u931726538_PoolAIssistant
User: u931726538_mbs_modproject
Pass: PoolAI2026!

Bootstrap Secret (for device provisioning):
  e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9
```

### Domain split — definitive map

Two subdomains, very different roles. Many files share names across the two deploy trees, so don't trust filenames alone — check which `*_deploy/` directory you're editing.

**`poolaissistant.modprojects.co.uk` — admin backend & all API**

Every machine-to-machine call goes here. Pis never make requests to `poolai.*`.

| Code dir (`web-portal/php_deploy/…`) | Live URL | Role |
|---|---|---|
| `api/` | `/api/*` | Device API (provision, heartbeat, snapshot, updates), Admin API, Portal API (`/api/portal/*`) |
| `admin/` | `/admin/*` | Admin dashboard (clients, devices, AI, software_updates) |
| `staff/` | `/staff/*` | Staff interface |
| `config/`, `includes/` | `/config/*`, `/includes/*` | Shared PHP libs |
| `portal/` | `/portal/*` | **Retired 2026-05-03** — files now 301-redirect to `poolai.*` (see Known quirks) |
| `scripts/` | `/scripts/*` | Server-side cron scripts |
| `database/` | not web-served | SQL migrations |
| (data tree) | `/data/updates/*.tar.gz` | Software update tarballs |

Server path: `/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/`
Email FROM: `noreply@poolaissistant.*`, `alerts@poolaissistant.*`
**FTP cannot reach this directly** — the FTP chroot lands on the customer-portal domain. Deploys hop via `_deploy_bundle.php` (see `deploy.manifest.json`) or via the cross-chroot `copy()` trick in software-update publishes.

**`poolai.modprojects.co.uk` — customer-facing portal**

Storefront. Mostly static pages + thin JS that makes API calls back to `poolaissistant.*/api/portal/`.

| Code dir (`web-portal/poolai_deploy/…`) | Live URL | Role |
|---|---|---|
| (root) | `/` | login, register, dashboard, device.php, account, qr.php, go.php (smart-link), install.php, offline.php (PWA) |

Server path: `/home/u931726538/domains/poolai.modprojects.co.uk/`
Email FROM: `noreply@poolai.*`
**FTP root** — this is where `u931726538.mbs` lands. Every deploy starts here.

### Who calls whom

- **Pi → admin domain only.** `persist.py:82` `backend_url`, `update_check.py:44` `UPDATE_SERVER_URL`. Pi DNS-preflights `poolaissistant.*` specifically.
- **Pi → customer domain for *display only*.** `main_ui.py:33-37` rewrites `poolaissistant.*` → `poolai.*` for QR codes / install hints. The Pi never makes HTTP requests to `poolai.*`.
- **Customer browser → admin domain.** `poolai_deploy/config/portal.php:31` defines `PORTAL_API_URL = 'https://poolaissistant.*/api/portal'`. The customer portal's data calls cross subdomains; CORS is configured on the Pi probe endpoint (`health.py:23-24`) and on the admin API.
- **Software update package flow.** Tarball uploaded to `poolai.*` via FTP, then a server-side `copy()` crosses the chroot boundary into `poolaissistant.*/data/updates/`.

### Rules of thumb

- *"Where does this PHP file deploy?"* — API endpoint or admin page? `php_deploy/`. Customer-facing chrome? `poolai_deploy/`.
- *"Which URL goes in a Pi config?"* — Always `poolaissistant.*`. Never `poolai.*` (only exception is the QR-code rewrite, which is for human eyes, not HTTP).
- *"Where does FTP land?"* — Always `poolai.*`. Server-side `copy()` is the bridge.

### Known architectural quirks

1. **Legacy customer portal at `poolaissistant.*/portal/*` was retired 2026-05-03.**
   Each `php_deploy/portal/*.php` now contains a 6-line stub that 301-redirects to the equivalent path on `poolai.*` (preserving query strings for verify/reset tokens). `php_deploy/includes/PortalAuth.php` and `PortalDevices.php` are kept — they're still consumed by `php_deploy/api/portal/readings.php`.
   The deploy-manifest glob (`deploy.manifest.json:17`) is unchanged so the stubs ship and overwrite the live files. Once redirect logs show the legacy URL is dead, drop the glob and let server-side cleanup remove the directory.

2. **`PORTAL_BASE_URL` still differs between `php_deploy/config/portal.php` and `poolai_deploy/config/portal.php`** (`…/portal` vs root). Now mostly cosmetic — the admin-side PortalAuth no longer fires emails since the pages that called it are redirect stubs. But if anything in `api/portal/*` ever sends mail using the admin-side config, the embedded link will 301-bounce to `poolai.*`. Worth normalising on the next pass.

3. **Shadow path that doesn't serve.** `/home/u931726538/public_html/poolaissistant/` exists on disk but is NOT served by `poolaissistant.modprojects.co.uk`. The live path is `/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/`. Don't FTP into the wrong one.

---

## Key API Endpoints

### Device Provisioning
```
POST /api/provision.php
Headers: x-bootstrap-secret: <bootstrap_secret>
Body: { "device_id": "...", "hostname": "...", "model": "...", "software_version": "..." }
Returns: { "api_key": "...", "device_id": "..." }
```

### Software Updates
```
GET /api/updates/check.php?current_version=6.3.0
Returns: { "update_available": true, "version": "6.4.0", "download_url": "...", "checksum": "..." }

GET /data/updates/update-v6.4.0.tar.gz
Direct download of update package
```

### Heartbeat (from Pi, every minute)
```
POST /api/heartbeat.php
Headers: Authorization: Bearer <api_key>
Body: { device telemetry, network metrics, AI sync payload }
```

### Snapshot (from Pi, every 6 minutes — bulk readings + alarms)
```
POST /api/device/snapshot.php
Headers: Authorization: Bearer <api_key>
Body: { "readings": [...], "alarms": [...], "health": {...} }
```

---

## Database Tables

Canonical schema lives in `php_deploy/database/*.sql` migrations. Don't trust DDL inlined into docs — it goes stale fast. Notable tables (names matter, columns evolve):

- `pi_devices` — registered Pi devices (the table the API joins to via API key)
- `device_health` — heartbeat telemetry rows
- `device_readings_latest`, `device_readings_history` — chemistry readings from Pi snapshots
- `device_alarms`, `alarm_events` — alarm state
- `device_commands` — admin-requested commands queued for the next heartbeat (e.g. "upload now")
- `software_updates` — published update tarballs (queried by `/api/updates/check.php`)
- `portal_users`, `user_devices` — customer accounts and device-link mappings
- `subscription_plans`, `user_subscriptions`, `payment_history`, `coupons`, `coupon_redemptions` — billing
- `ai_suggestions`, `ai_responses`, etc. — Claude-driven analysis history

---

## Deploying Software Updates

The canonical playbook lives in [`pi-software/CLAUDE.md`](../pi-software/CLAUDE.md#software-update-process) — package + checksum + FTP-to-FTP-root + cross-chroot deploy script. The deploy script (`deploy_update.php`) self-verifies the SHA256, upserts the `software_updates` row, deactivates older versions, and self-deletes. Most recent successful publish: v6.11.9 on 2026-05-03.

---

## Project Structure

```
web-portal/
├── CLAUDE.md              # This file
├── deploy.manifest.json   # Declarative deploy manifest (consumed by deploy.py)
├── php_deploy/            # → poolaissistant.modprojects.co.uk
│   ├── api/               #     Device API + Admin API + /api/portal/*
│   ├── admin/             #     Admin dashboard (clients, devices, AI, updates)
│   ├── staff/             #     Staff/timeclock interface
│   ├── config/            #     database.php, config.php (admin-domain)
│   ├── includes/          #     PortalAuth, PortalDevices (consumed by api/portal/*)
│   ├── portal/            #     RETIRED — 301-redirect stubs to poolai.* (kept until cleanup)
│   ├── scripts/           #     Server-side cron scripts
│   └── database/          #     SQL migrations
├── poolai_deploy/         # → poolai.modprojects.co.uk
│   ├── (root pages)       #     login, register, dashboard, device, account, qr, go, install, offline (PWA)
│   ├── config/, includes/ #     Shared portal libs (Subscription, PortalAuth, PortalDevices)
│   └── assets/            #     Static CSS/JS
└── backend/               # LEGACY: Node.js/Postgres version (not deployed)
```

See "Domain split" above for which URL each subtree maps to.

---

## Common Tasks

### Check if device is provisioned
```sql
SELECT * FROM pi_devices WHERE device_id = 'pi-xxxx-xxxx';
```

### View available updates
```sql
SELECT version, filename, is_active, created_at
FROM software_updates
ORDER BY created_at DESC;
```

### Deactivate an update
```sql
UPDATE software_updates SET is_active = 0 WHERE version = '6.3.0';
```

### View device activity
```sql
SELECT device_id, name, software_version, last_seen
FROM pi_devices
ORDER BY last_seen DESC;
```

---

## Important Notes

(For server paths and FTP chroot details, see "Domain split" above — those are no longer duplicated here.)

- **Bootstrap secret is hardcoded** on both server and Pi (`pi-software/PoolDash_v6/pooldash_app/persist.py` DEFAULTS).
- **Auto-update runs at 3 AM** on Pi devices via `update_check.timer`. Pis can also be updated manually via Settings → Check for Updates, or `sudo python3 /opt/PoolAIssistant/app/scripts/update_check.py --apply`.
- **Version comparison is semantic** — 6.4.0 > 6.3.0 > 6.2.5. The Pi only applies updates where server version > current version.

---

## Uptime Monitoring (degraded — read before relying on it)

**Workflow:** `.github/workflows/uptime.yml` → `.github/scripts/uptime_probe.sh`
Runs every 5 min and probes 7 endpoints across both subdomains.

**Current state (2026-04-26):** Hostinger's WAF rate-limits requests
from GitHub Actions runner IPs and returns HTTP 429 on most/all
endpoints. Real users in real browsers are unaffected — this is a
GitHub-IP-only issue.

To stop the resulting flood of failure emails, the probe now treats
**429 as "alive, WAF rate-limited"** and skips the marker check for
those responses. That keeps the workflow green but means the probe has
lost most of its diagnostic value: it can no longer detect the
silent-500 failure mode it was originally built to catch (PHP fatal
returning empty body with status 500 — the exact bug that hid a broken
admin login for weeks).

**What it still catches:** connection refused, DNS failures, hard 5xx
on the (often only one) endpoint that escapes the WAF on a given run.

**Upgrade path when uptime monitoring matters:** move to an external
service (e.g. UptimeRobot free tier). Their probe IPs are whitelisted
by Hostinger, so they see real responses and can do strict status +
content checks again.

---

## Related Projects
- **Pi Software**: `../pi-software/` (Flask app, has CLAUDE.md)
- **PoolDash_v6**: `../pi-software/PoolDash_v6/` (main Pi application)
