# PHP Surface Trim Plan

**Date:** 2026-06-12 · **Branch:** `reliability-revamp-2026-06-12`

Evidence-based classification of every PHP entry point across the three deploy
trees. Goal: shrink the attack/maintenance surface to what actually earns its
keep, without ever touching an endpoint the Pi depends on.

**Classifications**
- **KEEP** — has a live caller (evidence cited) or implements documented behaviour.
- **DELETE** — no caller anywhere in the repo AND documented/marked as retired or
  one-shot. Deletions are staged in this commit only, so the commit can be
  dropped wholesale.
- **UNSURE** — probably removable but needs a human decision; left untouched.

---

## ⚠️ Read this first: three things that bite

### 1. `deploy.py` NEVER deletes server-side files

Both `php_installer` and direct `ftp` modes only WRITE. Every file deleted in
this commit **stays live on the server** until someone removes it by hand.
The exact server paths to remove are listed in the
[Server-side cleanup pass](#server-side-cleanup-pass) section below.

### 2. Two live, unauthenticated endpoints — ✅ REMOVED FROM SERVER 2026-06-12

| URL | Problem | Status |
|---|---|---|
| `https://admin.modprojects.co.uk/admin/setup.php` | **No auth. Creates admin users.** Only guards against duplicate usernames — does NOT lock out once an admin exists. Header says "Delete this file after setup!" but it was never deleted. | Found HTTP 200 → **deleted via admin FTP, verified 404** |
| `https://poolaissistant.modprojects.co.uk/api/updates/add.php` | **No auth. Inserts rows into `software_updates`.** An attacker who can also place a tarball (or point at any reachable file) could queue a malicious "update" for the fleet; update signature enforcement is still in permissive rollout mode (`REQUIRE_SIGNATURE_DEFAULT = False`). Header says "should be protected or removed after use". | Found HTTP 400 (live) → **deleted via one-shot cleaner, verified 404**. Legacy `api/add_update.php` probed: not present. |

**Bonus findings removed the same day:** three unauthenticated
`deploy_fix_*.php` one-shots at the poolai docroot root (each HTTP hit
re-wrote API files in the poolaissistant docroot with code embedded at
write-time — a public regression button). Deleted via FTP, verified 404.
A stale `update-v6.9.5.tar.gz` also sits at the poolai docroot root —
harmless but worth removing on the next cleanup pass.

### 3. The server has Pi-critical files that are NOT in git — ✅ IMPORTED 2026-06-13

These were installed by one-shot installers (mostly from `brain/deploy/*`) and
never imported into `web-portal/`. The six below were fetched from the
poolaissistant docroot (via a one-shot base64-dump PHP, sha256-verified) and
committed to `web-portal/php_deploy/` so the repo now mirrors reality. **Still
must never be deleted server-side.**

| Server path (poolaissistant docroot) | Caller | Status |
|---|---|---|
| `api/updates/check.php` | **THE Pi update path** — `scripts/update_check.py:246` | imported + **refactored**: it hardcoded the DB password with an inline `new PDO(...)`; rewritten to use the shared `config/database.php` `db()` like every sibling, and the clean version redeployed to the server (verified both update paths still work). |
| `api/health.php` | `scripts/auto_provision.py:301` | imported verbatim |
| `api/chunks_status.php` | `scripts/chunk_manager.py:365`, `auto_provision.py:331` | imported verbatim (installed by `brain/deploy/install_chunks_api.php`) |
| `api/upload_chunk.php` | `scripts/chunk_manager.py:308` | imported verbatim (installed by `brain/deploy/install_chunks_api.php`) |
| `api/device_status.php` | `scripts/auto_provision.py:364` | imported verbatim (installed by `brain/deploy/install_device_status.php`) |
| `api/backup_settings.php` | `scripts/settings_backup.py:99` | imported verbatim |
| `api/add_update.php` | legacy docs only (`pi-software/PoolDash_v6/CLAUDE.md`) | NOT present on server (probed 2026-06-12) — nothing to import |

---

## php_deploy → poolaissistant.modprojects.co.uk (45 entry points)

### Pi-facing API — KEEP (the Pi calls these)

| File | Caller evidence |
|---|---|
| `api/provision.php` | `scripts/auto_provision.py:146` |
| `api/heartbeat.php` | `scripts/health_reporter.py:542` (also carries AI sync, alias sync, remote commands) |
| `api/command_complete.php` | `scripts/health_reporter.py:715` |
| `api/device/snapshot.php` | `scripts/cloud_upload.py:462` |
| `api/check_updates.php` | setup wizard, `pooldash_app/blueprints/main_ui.py` (`/setup/check-updates`) |
| `api/updates/download.php` | `download_url` returned by server-side `updates/check.php`; Pi downloads tarballs through it |
| `api/ai/heartbeat_extension.php` | not an endpoint — `require`d by `api/heartbeat.php:14` |

### Customer-portal API — KEEP (poolai.* browsers call these cross-origin)

| File | Caller evidence |
|---|---|
| `api/portal/link-code.php` | Pi UI (`main_ui.py:3345`) generates codes; portal redeems them. Base URL: `poolai_deploy/config/portal.php:31` (`PORTAL_API_URL`) |
| `api/portal/link-status.php` | Pi UI (`main_ui.py:3691`) |
| `api/portal/readings.php` | portal device page charts via `PORTAL_API_URL` |

### Redirect stubs — KEEP (they ARE the documented behaviour)

- `admin/*.php` — 19 identical one-line **308** stubs → `admin.modprojects.co.uk`
  (admin moved 2026-05-08). Evidence: every file in `deploy.lock.json`
  `admin-backend` section shares hash `cdcf1ab7…`.
- `portal/*.php` — 10 per-page **301** stubs → `poolai.modprojects.co.uk`
  (portal retired 2026-05-03).

*Simplification option (not staged):* both stub sets could be replaced by two
`.htaccess` RewriteRules, deleting 29 files. Do it as its own change if wanted.

### Cron scripts — KEEP

| File | Evidence |
|---|---|
| `scripts/check_device_health.php` | pipeline-health alerter (3-state, deployed 2026-05-11, runs on hPanel cron) |
| `scripts/event_log_retention.php` | audit-log retention (deployed 2026-05-14; cron may still need configuring) |

### Shared libs / config — KEEP (do not touch)

`includes/api_helpers.php`, `includes/AuditLog.php`, `includes/auth.php`
(device API-key auth — required by snapshot/link-code/link-status/
check_device_health, **not** an admin leftover), `includes/PortalAuth.php`,
`includes/PortalDevices.php`, `config/*.php`.

### DELETE — staged in this commit

| File | Evidence |
|---|---|
| `api/updates/add.php` | **Unauthenticated `software_updates` insert** (see warning above). No caller: releases use one-shot `deploy_update.php` scripts; nothing in any repo references it. |
| `api/ai/ask_me.php` | Zero callers. Designed for direct Pi POST (`ai-assistant/docs/PLAN.md`) but the shipped implementation syncs AI via the heartbeat (`health_reporter.py:812-890`). Admin/staff use the separate `admin_deploy/api/ai/*` copies. Only Swanwood (v6.11.13) exists — no old fleet to break. |
| `api/ai/response.php` | Same evidence as `ask_me.php`. |
| `api/ai/suggestion_feedback.php` | Same evidence as `ask_me.php`. |

### UNSURE — left untouched, needs a decision

| File | Why unsure |
|---|---|
| `api/device_alias.php` | Documented split design (Pi-side API-key auth, `web-portal/CLAUDE.md`), but the current Pi never calls it — alias sync rides the heartbeat (`alias_sync` in the response). Keep if a future Pi build uses the GET path; otherwise removable. |

---

## admin_deploy → admin.modprojects.co.uk (44 entry points)

### Admin UI + API — KEEP

All session-auth'd (`requireAdmin()`); pages link each other and call their own
`api/*` (e.g. `admin/clients.php:426` → `api/admin/client_actions.php`,
`admin/ai_questions.php` → `api/ai/questions.php|queue.php`,
`admin/index.php:643` → `api/device_alias.php`). Deployed 2026-05-14
(`deploy.lock.json` `admin-domain`).

`admin/{index,login,logout,audit,bootstrap_codes,clients,client_detail,device}.php`,
`admin/ai_{analytics,dashboard,learnings,questions,responses,settings,suggestions}.php`,
`api/admin/{_verify,client_actions}.php`,
`api/{admin_device_command,admin_health,admin_request_upload,admin_update_setting}.php`,
`api/ai/{generate,norms,profiles,questions,queue,responses,suggestions}.php`,
`api/{clear_device_issues,delete_device,device_alias}.php`,
`includes/*`, `config/*`, root `index.php`.

### Staff PWA — KEEP (verify it's actually used)

`staff/{index,login,logout,icon}.php`, `staff/api/{checkin,dashboard}.php` —
self-contained check-in app; `staff/assets/app.js` calls its own API plus
`api/ai/{suggestions,responses}.php`. Deployed 2026-05-14. **Confirm staff
actually use it; if not, this is ~6 files + 4 assets of removable surface.**

### DELETE — staged in this commit

| File | Evidence |
|---|---|
| `admin/setup.php` | **Unauthenticated admin-user creation, live right now** (HTTP 200, see warning above). One-shot installer ("Delete this file after setup!") that was never deleted. Admin user exists; migrations applied. |
| `admin/fix_devices.php` | One-shot column fixer, header says "DELETE AFTER USE". The `alias` column it adds has existed since `database/migration_alias.sql`; the whole admin UI depends on it daily. Admin-guarded (302 to login), so not urgent — just dead. |
| `admin/_run_migration_network.php` | One-shot migration runner for `device_health.network_json` (v6.11.2 network-health feature, live since 2026-04). Self-deletes server-side after success; the local copy only re-uploads it on every deploy. Admin-guarded + idempotent, so not urgent — just dead. |

### UNSURE — RESOLVED 2026-06-13

| File | Decision |
|---|---|
| `admin/seed_questions.php` | **DELETED** (git + server) — orphaned dev seeder, no references. |
| `admin/queue_test.php` (page) | **DELETED** (git + server) — orphaned; superseded by the inline "Test AI" button (`admin/index.php:437`). |
| `api/queue_test_question.php` | **KEPT** — live: powers the "Test AI" button on every device card. |
| `staff/*` PWA (10 files) | **DELETED** (git + server, tree removed) — owner confirmed unused; never linked from admin nav. The `staff_checkins` DB table is left in place (harmless, self-created by the old endpoint; drop manually if desired). |
| `php_deploy/api/device_alias.php` (Pi-side) | **KEPT** — dead today (Pi syncs alias via heartbeat, which is itself disabled), but the natural Pi-side endpoint if alias sync is ever re-enabled. Revisit with the alias-sync feature, not standalone. |

---

## poolai_deploy → poolai.modprojects.co.uk (16 entry points)

### All KEEP — live customer portal

| File(s) | Evidence |
|---|---|
| `index,login,register,logout,dashboard,device,account.php` | the portal itself; session flows via `includes/PortalAuth.php` |
| `forgot-password,reset-password,verify-email.php` | email/account flows linked from login/register |
| `go.php` | Pi smart-link QR target (`main_ui.py` `_smart_link_qr` → `{poolai}/go.php?d=<device_id>`) |
| `qr.php` | QR image generator used by smart-link/install flows |
| `install.php`, `offline.php` | PWA install + offline pages (v6.11.6), referenced by `service-worker.js`/`manifest.json` |
| `privacy.php`, `terms.php` | legal pages linked from register/footer |
| `includes/*`, `config/*` | shared libs (`Subscription.php` powers the settings-page subscription card) |

---

## Server-side cleanup pass (manual — deploy.py cannot do this)

After this commit merges and deploys, remove by hand (FTP / hPanel file manager):

**URGENT (security): ✅ DONE 2026-06-12** — `admin/setup.php` (admin docroot) and
`api/updates/add.php` (poolaissistant docroot) deleted and verified 404, plus the
three `deploy_fix_*.php` one-shots at the poolai docroot.

**FTP layout discovered while doing it (corrects earlier docs):**
- admin FTP chroot **root** IS the admin docroot (`/admin/...`, not
  `public_html/...` — the empty `/public_html` dir there is an artifact).
- mbs FTP chroot root is the **poolai.\*** docroot. The poolaissistant docroot is
  NOT FTP-reachable; server-side deletions there need the one-shot self-deleting
  PHP pattern (upload via mbs FTP, execute via `https://poolai.*/<file>.php`).
- `.env` files at both docroots are blocked by `.htaccess` (verified 403).

**Routine (dead code):**
```
admin.modprojects.co.uk docroot:      admin/fix_devices.php
                                      admin/_run_migration_network.php   (may already be gone — self-deletes)
poolaissistant docroot:               api/ai/ask_me.php
                                      api/ai/response.php
                                      api/ai/suggestion_feedback.php
```

**Also recommended:** probe whether legacy `api/add_update.php` still exists on
the poolaissistant docroot; if yes, remove it too (same risk as `updates/add.php`).

**Do NOT remove** anything in the "server has Pi-critical files not in git"
table above. Import those into `web-portal/php_deploy/` instead.
