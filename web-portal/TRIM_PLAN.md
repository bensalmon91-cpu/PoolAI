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

### 2. Two live, unauthenticated endpoints need URGENT server-side removal

| URL | Problem | Live check (2026-06-12) |
|---|---|---|
| `https://admin.modprojects.co.uk/admin/setup.php` | **No auth. Creates admin users.** Only guards against duplicate usernames — does NOT lock out once an admin exists. Header says "Delete this file after setup!" but it was never deleted. | HTTP 200, form renders |
| `https://poolaissistant.modprojects.co.uk/api/updates/add.php` | **No auth. Inserts rows into `software_updates`.** An attacker who can also place a tarball (or point at any reachable file) could queue a malicious "update" for the fleet; update signature enforcement is still in permissive rollout mode (`REQUIRE_SIGNATURE_DEFAULT = False`). Header says "should be protected or removed after use". | HTTP 400 (live, parses params) |

Delete these from the server **before** worrying about anything else in this plan.

### 3. The server has Pi-critical files that are NOT in git

These were installed by one-shot installers (mostly from `brain/deploy/*`) and
never imported into `web-portal/`. **They must never be deleted server-side**,
and a follow-up should download them into git so the repo mirrors reality:

| Server path (poolaissistant docroot) | Caller | Evidence |
|---|---|---|
| `api/updates/check.php` | **THE Pi update path** — `scripts/update_check.py:246` | live: HTTP 200 |
| `api/health.php` | `scripts/auto_provision.py:301` | |
| `api/chunks_status.php` | `scripts/chunk_manager.py:365`, `auto_provision.py:331` | installed by `brain/deploy/install_chunks_api.php` |
| `api/upload_chunk.php` | `scripts/chunk_manager.py:308` | installed by `brain/deploy/install_chunks_api.php` |
| `api/device_status.php` | `scripts/auto_provision.py:364` | installed by `brain/deploy/install_device_status.php` |
| `api/backup_settings.php` | `scripts/settings_backup.py:99` | |
| `api/add_update.php` | legacy docs only (`pi-software/PoolDash_v6/CLAUDE.md`) | presence unverified — if live and unauthenticated, same risk class as `updates/add.php` |

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

### UNSURE — left untouched

| File | Why unsure |
|---|---|
| `admin/seed_questions.php` | Dev tool (seeds AI question templates). Admin-guarded. Useful again if AI question bank needs re-seeding. |
| `admin/queue_test.php` + `api/queue_test_question.php` | Dev tool pair for testing the AI question queue. Admin-guarded. Keep while AI features are still being tuned? |

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

**URGENT (security):**
```
admin.modprojects.co.uk docroot:      admin/setup.php
poolaissistant docroot:               api/updates/add.php
  (= /home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/api/updates/add.php)
```

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
