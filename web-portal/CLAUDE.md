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
API backend: https://poolaissistant.modprojects.co.uk  (Pi API + customer-portal API; no browser pages)
Admin UI:    https://admin.modprojects.co.uk  (admin panel: /admin/) — IN FLIGHT 2026-05-08
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

**Three subdomains as of 2026-05-08.** Many files share names across the deploy trees, so don't trust filenames alone — check which `*_deploy/` directory you're editing.

**`poolaissistant.modprojects.co.uk` — Pi-facing + customer-portal API only**

Every Pi machine-to-machine call goes here. No browser-facing pages: `/admin/*` is now 308-redirect stubs to `admin.*`, and `/portal/*` is 301-redirect stubs to `poolai.*` (retired earlier, 2026-05-03).

| Code dir (`web-portal/php_deploy/…`) | Live URL | Role |
|---|---|---|
| `api/` (Pi-facing) | `/api/heartbeat.php`, `/api/provision.php`, `/api/device/snapshot.php`, `/api/check_updates.php`, `/api/command_complete.php`, `/api/device_alias.php`, `/api/updates/*` | Pi API — auth via API key / bootstrap secret |
| `api/portal/` | `/api/portal/*` | Customer-portal data API — auth via PortalAuth, called cross-origin from `poolai.*` browsers |
| `api/ai/{ask_me,response,suggestion_feedback,heartbeat_extension}` | `/api/ai/*` | AI Q&A endpoints called by Pis (separate from the admin AI endpoints which moved to `admin.*`) |
| `admin/` | `/admin/*` | **Retired 2026-05-08** — every file is a 308-redirect stub to `admin.*` |
| `portal/` | `/portal/*` | **Retired 2026-05-03** — 301-redirect stubs to `poolai.*` (see Known quirks) |
| `config/`, `includes/` | not web-served | Shared PHP libs (PortalAuth, PortalDevices, api_helpers, auth) |
| `scripts/` | `/scripts/*` | Server-side cron scripts |
| `database/` | not web-served | SQL migrations |
| (data tree) | `/data/updates/*.tar.gz` | Software update tarballs |

Server path: `/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/`
Email FROM: `noreply@poolaissistant.*`, `alerts@poolaissistant.*`
**FTP cannot reach this directly** — the FTP chroot lands on `poolai.*`. Deploys hop via `_deploy_bundle.php` (see `deploy.manifest.json`) or via the cross-chroot `copy()` trick in software-update publishes.

**`admin.modprojects.co.uk` — admin UI + admin-only API** *(in flight, 2026-05-08)*

Same-origin between admin pages and admin API: no CORS, no cross-subdomain cookies. Admin auth (`includes/auth.php`'s `requireAdmin()`) is enforced inside the new chroot only.

| Code dir (`web-portal/admin_deploy/…`) | Live URL | Role |
|---|---|---|
| `admin/` | `/admin/*` | Admin dashboard — clients, devices, AI suggestions/responses/questions, bootstrap codes, software updates |
| `staff/` | `/staff/*` | Staff timeclock interface (uses `requireAdmin()`, lives with admin) |
| `api/admin/` | `/api/admin/*` | Admin REST endpoints — `_verify.php`, `client_actions.php` |
| `api/admin_*.php` | `/api/admin_*.php` | Admin device controls — `admin_device_command`, `admin_health`, `admin_request_upload`, `admin_update_setting` |
| `api/{clear_device_issues,delete_device,queue_test_question,device_alias}` | `/api/*` | Admin operations on devices (admin-session auth) |
| `api/ai/{generate,norms,profiles,questions,queue,responses,suggestions}` | `/api/ai/*` | Admin AI endpoints (the Pi-facing `/api/ai/{ask_me,response,suggestion_feedback}` stay on `poolaissistant.*`) |
| `config/`, `includes/` | not web-served | Admin-side shared libs (auth.php, AdminClients, AdminDevices, RemoteSettings, claude_api, api_helpers) |
| `index.php`, `.htaccess` | `/` | Bare-domain redirect to `/admin/` + security headers |

Server path: `/home/u931726538/domains/admin.modprojects.co.uk/` *(to be confirmed once hPanel subdomain is created)*
Email FROM: TBD (likely keep `noreply@poolaissistant.*` — no functional change)
**FTP:** new dedicated FTP user expected (`POOLAI_ADMIN_FTP_USER` in root `.env` once provisioned). Cleanest case is its own chroot like `poolai.*`'s setup.

**`poolai.modprojects.co.uk` — customer-facing portal**

Storefront. Mostly static pages + thin JS that makes API calls back to `poolaissistant.*/api/portal/*`.

| Code dir (`web-portal/poolai_deploy/…`) | Live URL | Role |
|---|---|---|
| (root) | `/` | login, register, dashboard, device.php, account, qr.php, go.php (smart-link), install.php, offline.php (PWA) |

Server path: `/home/u931726538/domains/poolai.modprojects.co.uk/`
Email FROM: `noreply@poolai.*`
**FTP root** — `u931726538.mbs` lands here. `php_deploy/` deploys hop through this chroot via `_deploy_bundle.php`.

### Who calls whom

- **Pi → `poolaissistant.*` only.** `persist.py:82` `backend_url`, `update_check.py:44` `UPDATE_SERVER_URL`. Pi DNS-preflights `poolaissistant.*` specifically. **Pis never call `admin.*` or `poolai.*`** (HTTP-wise — the QR-code URL rewrite to `poolai.*` is for human eyes only).
- **Admin browser → `admin.*` only.** Admin pages and admin API are same-origin on this subdomain. No cross-subdomain calls.
- **Customer browser → `poolaissistant.*` for data.** `poolai_deploy/config/portal.php:31` defines `PORTAL_API_URL = 'https://poolaissistant.*/api/portal'`. CORS is configured on the admin-domain customer-portal API endpoints.
- **Software update package flow.** Tarball uploaded to `poolai.*` via FTP, then a server-side `copy()` crosses the chroot boundary into `poolaissistant.*/data/updates/`.

### Rules of thumb

- *"Where does this PHP file deploy?"* —
  - Pi API or customer-portal API? → `php_deploy/`
  - Admin UI or admin API? → `admin_deploy/`
  - Customer-facing browser pages? → `poolai_deploy/`
- *"Which URL goes in a Pi config?"* — Always `poolaissistant.*`. Never `poolai.*` or `admin.*`.
- *"Where does FTP land?"* — `poolai.*` for the customer portal; `admin.*` for admin (once provisioned); `poolaissistant.*` only via the cross-chroot `copy()` hop.

### Known architectural quirks

1. **Admin moved to `admin.modprojects.co.uk` 2026-05-08.**
   Admin UI + admin-only API now live in `web-portal/admin_deploy/`. Each retired admin file in `php_deploy/admin/*.php` is a 6-line 308-redirect stub to the equivalent path on `admin.*` (308 preserves the HTTP method so admin form POSTs don't downgrade to GET). The corresponding admin-only API endpoints have been **deleted** from `php_deploy/api/` rather than stubbed — they were never called by anything other than admin pages, which now live in the new chroot and use same-origin URLs.
   `api/device_alias.php` was split: Pi-side (API-key auth) stays in `php_deploy/api/`, admin-side (session auth) moved to `admin_deploy/api/`. Same DB table, single auth concern per endpoint.
   **Pre-existing bug fixed during the move:** `admin_deploy/api/ai/generate.php` had `require_once __DIR__ . '/../includes/claude_api.php'` — needed two `..` (the file is at `api/ai/`, not `api/`). Would have 500'd the admin "generate AI" button on the live site; never noticed because nobody clicked it.

2. **Legacy customer portal at `poolaissistant.*/portal/*` was retired 2026-05-03.**
   Each `php_deploy/portal/*.php` now contains a 6-line stub that 301-redirects to the equivalent path on `poolai.*` (preserving query strings for verify/reset tokens). `php_deploy/includes/PortalAuth.php` and `PortalDevices.php` are kept — they're still consumed by `php_deploy/api/portal/readings.php`.
   The deploy-manifest glob (`deploy.manifest.json`) is unchanged so the stubs ship and overwrite the live files. Once redirect logs show the legacy URL is dead, drop the glob and let server-side cleanup remove the directory.

3. **`PORTAL_BASE_URL` still differs between `php_deploy/config/portal.php` and `poolai_deploy/config/portal.php`** (`…/portal` vs root). Now mostly cosmetic — the admin-side PortalAuth no longer fires emails since the pages that called it are redirect stubs. But if anything in `api/portal/*` ever sends mail using the admin-side config, the embedded link will 301-bounce to `poolai.*`. Worth normalising on the next pass.

4. **Shadow path that doesn't serve.** `/home/u931726538/public_html/poolaissistant/` exists on disk but is NOT served by `poolaissistant.modprojects.co.uk`. The live path is `/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/`. Don't FTP into the wrong one.

5. **Duplicated includes/config across deploy trees.** `config/database.php`, `config/config.php`, `includes/auth.php`, and `includes/api_helpers.php` exist in BOTH `php_deploy/` and `admin_deploy/` — both deploy targets need them. Keep them in sync when editing (or factor into a shared dir + post-build copy if drift becomes a problem). `includes/PortalAuth.php`, `PortalDevices.php` and `config/portal.php` live only in `php_deploy/` (admin doesn't use them). `includes/AdminClients.php`, `AdminDevices.php`, `RemoteSettings.php`, `claude_api.php` live only in `admin_deploy/` (Pi/customer-portal don't use them).

6. **admin.* Hostinger chroot mismatch (discovered + worked-around 2026-05-08).**
   The FTP user `u931726538.claudeadmin` lands at PWD `/public_html` on connect, but **Apache serves from one level above** (the chroot root, where `default.php` lives — Hostinger's auto-generated landing page). Empirically verified by uploading probe files to both paths and seeing which one the web server returned. The "Directory: /home/u931726538/domains/admin.modprojects.co.uk/public_html" that hPanel showed in the FTP-account UI is misleading — it's the FTP user's default-PWD, NOT the web docroot.
   **Workaround in code:** `deploy.py` now does `ftp.cwd("/")` immediately after connect (was missing). `deploy.manifest.json` for `admin-domain` uses `ftp_base_subdir: ""` (was `"public_html"`). Files now upload to chroot root and Apache serves them.
   **Bootstrap step:** `.env` is NOT in the deploy globs (deploy.py's glob list filters by extension, dotfiles excluded). On first deploy of admin.*, the `.env` was FTP'd manually. When DB/secret creds rotate, **also FTP a fresh `admin_deploy/.env` to chroot root** — `deploy.py` will not do it automatically.

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
├── php_deploy/            # → poolaissistant.modprojects.co.uk (Pi API + customer-portal API)
│   ├── api/               #     Pi-facing endpoints + /api/portal/* (customer-portal data API)
│   │   ├── ai/            #     Pi-facing AI: ask_me, response, suggestion_feedback, heartbeat_extension
│   │   ├── device/        #     snapshot.php (Pi 6-min upload)
│   │   ├── portal/        #     Customer-portal data API (link-code, link-status, readings)
│   │   └── updates/       #     Pi update download + add
│   ├── admin/             #     RETIRED 2026-05-08 — 308-redirect stubs to admin.*
│   ├── portal/            #     RETIRED 2026-05-03 — 301-redirect stubs to poolai.*
│   ├── config/            #     database.php, config.php, portal.php (PortalAuth config)
│   ├── includes/          #     PortalAuth, PortalDevices, api_helpers, auth (still needed by scripts/)
│   ├── scripts/           #     Server-side cron scripts (check_device_health, etc.)
│   └── database/          #     SQL migrations
├── admin_deploy/     # → admin.modprojects.co.uk (admin UI + admin-only API)  [NEW 2026-05-08]
│   ├── admin/             #     Admin dashboard (clients, devices, AI, updates, bootstrap codes)
│   ├── staff/             #     Staff/timeclock interface (uses requireAdmin)
│   ├── api/               #     Admin-only API: api/admin/, api/admin_*.php, api/ai/{generate,norms,profiles,questions,queue,responses,suggestions}, plus admin-side device_alias/clear_device_issues/delete_device/queue_test_question
│   ├── config/            #     database.php, config.php (duplicated from php_deploy)
│   ├── includes/          #     auth, api_helpers (duplicated) + AdminClients, AdminDevices, RemoteSettings, claude_api (admin-only)
│   ├── index.php          #     Bare-domain → /admin/ redirect
│   └── .htaccess          #     Security headers + bare-domain redirect
├── poolai_deploy/         # → poolai.modprojects.co.uk (customer-facing portal)
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
