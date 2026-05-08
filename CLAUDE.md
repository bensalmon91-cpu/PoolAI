# PoolAIssistant Project - Cloud Integration Roadmap

**Last Updated:** 2026-05-08 · **Pi software current:** v6.11.10

This master document tracks the PoolAIssistant ecosystem including the Pi software, web portal, and cloud integration features.

## Current state snapshot

- **Pi software (released):** v6.11.10 (alarm-lifecycle hardening + first unit-test infra). Earlier shipped versions: v6.11.5 (WiFi static-IP preflight + DNS fallback), v6.11.6 (smart-link QR + PWA install + cloud chemistry + subscription card), v6.11.7–8 (review polish), v6.11.9 (alarm cleanup — superseded by v6.11.10 which fixes a dead-code sweep).
- **Active Pis:** Swanwood (production) @ `10.0.30.247` (WiFi DHCP per 2026-04-26 recovery), tvcctv (second unit) @ `10.0.30.131`. Both will land on v6.11.10 at the next 03:00 update cron.
- **Web portal:** legacy `poolaissistant.*/portal/*` retired 2026-05-03 (10 PHP files now 301-redirect to `poolai.*`). Customer portal at `poolai.modprojects.co.uk` is the canonical forward direction.
- **Admin split (in flight, 2026-05-08):** admin UI + admin-only API moving from `poolaissistant.*/admin/*` to a new subdomain `admin.modprojects.co.uk`. Local code split is done (`web-portal/admin_deploy/`); deploy waits on hPanel subdomain creation + new FTP creds. `poolaissistant.*` retains all Pi-facing API and the customer-portal API; admin URLs there 308-redirect to `admin.*`.
- **Next milestone:** fresh SD card install — validates the v6.11.3 installer cleanup end-to-end on a clean Pi. Plan logged in `pi-software/CLAUDE.md` under "Fresh SD Card Install Plan".
- **Open backlog:** 2 items — hardcoded `poolai:12345678` default password (security), SSH/sudo TTY docs. See `.claude/projects/.../memory/project_installer_improvements.md`.

---

## Project Structure

```
PoolAIssistant-Project/
├── pi-software/             # Raspberry Pi application
│   └── PoolDash_v6/         # Main Pi codebase (Flask + Modbus)
├── web-portal/              # Server-side components
│   ├── php_deploy/          # Pi-facing + customer-portal API (poolaissistant.modprojects.co.uk)
│   ├── admin_deploy/        # Admin UI + admin-only API (admin.modprojects.co.uk)
│   ├── poolai_deploy/       # Customer portal (poolai.modprojects.co.uk)
│   └── database/            # SQL schema migrations
├── brain/                   # Swanwood Spa analytics (separate project)
└── CLAUDE.md                # This file
```

See individual CLAUDE.md files for detailed documentation:
- `pi-software/CLAUDE.md` — **primary docs** (install, deploy, fleet, fresh SD card plan)
- `pi-software/PoolDash_v6/CLAUDE.md` — Flask app layout and known UX papercuts
- `web-portal/CLAUDE.md` — Server deployment, API endpoints, **domain split map** (which code lives on `poolaissistant.*` vs `poolai.*`)

**Domain split TL;DR (three subdomains):**
- `poolaissistant.modprojects.co.uk` = Pi-facing API (provision, heartbeat, snapshot, updates) + customer-portal API (`/api/portal/*`). No browser-facing pages — `/admin/*` here is now 308-redirect stubs to `admin.*`.
- `admin.modprojects.co.uk` *(in flight, 2026-05-08)* = admin UI + admin-only API. Same-origin: admin pages and admin API live here together, no CORS or cross-subdomain cookies.
- `poolai.modprojects.co.uk` = customer portal (browser-facing). Browsers here call `poolaissistant.*/api/portal/*` cross-origin.

FTP for `poolai.*` lands directly in its docroot. `poolaissistant.*` deploys hop via a server-side `copy()` from `poolai.*` (FTP can't reach the admin-backend chroot). `admin.*` will get its own FTP creds — direct deploy. Full table + known quirks in `web-portal/CLAUDE.md`.

---

## Quick Reference - Endpoints & Credential Map

**Live secrets are no longer stored here.** They live in `PoolAIssistant-Project/.env`
(gitignored, single source of truth — see `scripts/consolidate_env.py`). This
section is now a *map* of which key in `.env` corresponds to which service.

```
=== ADMIN UI ===
  URL: https://admin.modprojects.co.uk        (NEW — in flight 2026-05-08)
  Admin: https://admin.modprojects.co.uk/admin/
  (Pre-cutover, admin still lives at https://poolaissistant.modprojects.co.uk/admin/.
   Once the new subdomain is provisioned and deployed, the old URL 308-redirects.)

=== API BACKEND (Pi-facing + customer-portal API) ===
  URL: https://poolaissistant.modprojects.co.uk
  Pi endpoints: /api/heartbeat.php, /api/provision.php, /api/device/snapshot.php, /api/check_updates.php, ...
  Customer-portal API: /api/portal/*

=== CUSTOMER PORTAL ===
  URL: https://poolai.modprojects.co.uk

=== FTP (Customer Portal — for code deploy) ===
  Host: SFTP_HOST          User: u931726538.mbs       Pass: SFTP_PASSWORD
  NOTE: FTP is chrooted to poolai.modprojects.co.uk, NOT poolaissistant!
  (Brain uses a different FTP account — u931726538.piaccess — for /data/chunks/)

=== FTP (Admin UI — admin.*) ===
  Host: POOLAI_ADMIN_FTP_HOST       User: POOLAI_ADMIN_FTP_USER       Pass: POOLAI_ADMIN_FTP_PASS
  Provisioned 2026-05-08. Real values in root .env (gitignored).
  FTP chroot lands one level above the docroot, so deploy.manifest.json
  uses ftp_base_subdir: "public_html" to upload into the right place.

=== DATABASE (Shared MySQL on Hostinger) ===
  Host: DB_HOST            Name: DB_NAME
  User: DB_USER            Pass: DB_PASS

=== PI SSH ACCESS ===
  Username: poolai
  Password: (hardcoded default — see backlog: rotate per-Pi, currently 12345678)
  Sudo: NOPASSWD configured

=== BOOTSTRAP SECRET (device provisioning) ===
  Value: BOOTSTRAP_SECRET   (used by web-portal admin and ai-assistant/php)
```

**⚠️ History note:** Earlier commits of this file contained these secrets in
plaintext. Removing them here does not remove them from git history. If true
rotation is desired:
1. Rotate the FTP password, DB password, and BOOTSTRAP_SECRET on the server.
2. Update `PoolAIssistant-Project/.env` and the deploy-folder mirrors.
3. Optionally `git filter-repo` to scrub history (separate decision).

The Pi SSH default password is a separate, longer-running backlog item
(per the "Open backlog" section above) — not in scope for this consolidation.

---

## Cloud Integration - Client Portal & Data Sync

### Purpose

The PoolAIssistant Cloud Portal allows pool operators to **monitor their pool systems remotely** from any web browser. Features include:

- Real-time pool chemistry readings (pH, chlorine, ORP, temperature)
- System health monitoring (controller connectivity, alarms, errors)
- Historical trends and maintenance logs
- Email alerts for out-of-range readings
- AI-powered maintenance recommendations

### User Workflow

```
1. REGISTRATION
   └─> User visits poolai.modprojects.co.uk
   └─> Creates account (email + password)
   └─> Verifies email address

2. DEVICE LINKING
   └─> On Pi: Settings → Portal → Generate Link Code
   └─> Pi displays 6-character code (valid 15 minutes)
   └─> User enters code on portal dashboard
   └─> Device now appears in user's account

3. DAILY MONITORING
   └─> User logs into portal
   └─> Dashboard shows all linked devices with status
   └─> Click device → See latest readings (updated every 6 min)
   └─> View charts for trends (pH over 24h, chlorine over week)
   └─> Check active alarms and maintenance reminders

4. REMOTE TROUBLESHOOTING
   └─> Get notified of critical alarms via email
   └─> View detailed alarm history and patterns
   └─> Check AI suggestions for corrective actions
   └─> Review maintenance log entries
```

### Data Flow (6-Minute Snapshots)

```
┌──────────────────┐     Every 6 min      ┌──────────────────────┐
│   Pi Device      │ ──────────────────── │   Cloud Server       │
│                  │      HTTPS POST      │                      │
│  Modbus Logger   │   - Latest readings  │  MySQL Database      │
│  (1min poll)     │   - Health metrics   │  ├─ device_readings  │
│       ↓          │   - Active alarms    │  ├─ device_health    │
│  SQLite DB       │   - Controller status│  └─ device_alarms    │
│       ↓          │                      │         ↓            │
│  Upload Timer    │   Device identified  │  Portal Web UI       │
│  (6min)          │   by API key         │  ├─ Dashboard        │
│                  │                      │  ├─ Charts           │
└──────────────────┘                      │  └─ Alarms           │
                                          └──────────────────────┘
```

**Why 6-Minute Intervals?**
- Pool chemistry changes slowly (pH drift takes hours)
- Catches alarm conditions within reasonable time
- ~240 uploads/day per device is manageable
- Syncs well with Pi's 1-minute logging interval (6 readings per upload)

---

## Implementation Phases

### Phase 1: Pi-Side Upload Service ✅ PRIORITY: HIGH
**Goal:** Pi automatically uploads snapshot every 6 minutes

**Files:**
- `scripts/cloud_upload.py` - Upload service script
- `scripts/systemd/poolaissistant_upload.service` - Systemd service
- `scripts/systemd/poolaissistant_upload.timer` - 6-minute timer
- `pooldash_app/persist.py` - Upload settings

**Settings Added:**
```python
"cloud_upload_enabled": True,
"cloud_upload_interval_minutes": 6,
"cloud_upload_last_ts": "",
"cloud_upload_last_status": "",
```

### Phase 2: Server-Side API Endpoint ✅ PRIORITY: HIGH
**Goal:** Server receives and stores Pi snapshots

**Files:**
- `php_deploy/api/device/snapshot.php` - Receive snapshots
- `database/schema_readings.sql` - Readings table migration

**API Endpoint:** `POST /api/device/snapshot.php`
- Auth: `Authorization: Bearer <api_key>`
- Input: JSON payload with readings, health, alarms
- Response: `{"ok": true, "next_upload_at": "..."}`

### Phase 3: Portal Dashboard Enhancement ✅ PRIORITY: MEDIUM
**Goal:** Display live data from cloud

**Files:**
- `php_deploy/portal/device.php` - Show latest readings
- `php_deploy/includes/PortalDevices.php` - Add data methods

**Features:**
- Reading Cards - Display latest pH, Cl, ORP, Temp with color-coded status
- Last Updated - Show "Updated 3 minutes ago"
- Status Indicators - Green/Yellow/Red based on thresholds

### Phase 4: Historical Charts ⏳ PRIORITY: MEDIUM
**Goal:** Show trends over time

**Features:**
- 24-Hour Overview - All metrics on single chart
- Weekly Trends - One chart per metric
- Data API: `GET /api/portal/device/{id}/readings?range=24h&metric=pH`

### Phase 5: Alarm Display & Notifications ⏳ PRIORITY: MEDIUM
**Goal:** Show active alarms and send email alerts

**Features:**
- Active Alarms Panel - List of current alarms with duration
- Alarm History - Recent alarm events
- Email Alerts - Critical alarm → immediate email

### Phase 6: Mobile Optimization ⏳ PRIORITY: LOW
**Goal:** Responsive design for phone/tablet

### Phase 7: AI Integration ✅ PRIORITY: HIGH
**Goal:** Portal displays AI insights and allows user interaction

**Features:**
- AI Suggestions Panel with priority badges
- AI Analysis Summary (water quality grade, reliability grade)
- Ask AI Feature for user questions
- Proactive Alerts

### Phase 8: Admin Backend - Client Management ✅ PRIORITY: HIGH
**Goal:** Admin can view and manage all portal clients

**Files:**
- `php_deploy/admin/clients.php` - Client list view
- `php_deploy/admin/client_detail.php` - Single client detail
- `php_deploy/includes/AdminClients.php` - Client management class

### Phase 9: Subscription & Payment System ✅ PRIORITY: HIGH
**Goal:** Clients pay monthly subscription for portal access

**Payment Provider:** Stripe

**Database Tables:**
- `subscription_plans` - Basic/Pro/Enterprise tiers
- `user_subscriptions` - Active subscriptions
- `payment_history` - Payment records

**Subscription Flow:**
1. SIGNUP (14-day free trial)
2. PAYMENT (Stripe Checkout)
3. RENEWAL (automatic monthly/yearly)
4. CANCELLATION (access until period end)

### Phase 10: Account Suspension & Enforcement ✅ PRIORITY: HIGH
**Goal:** Automatically suspend non-paying accounts

**Features:**
- Daily billing cron job
- Grace period for past_due accounts
- Manual admin actions (suspend, activate, extend)

### Phase 11: Coupon & Promo Code System ✅ PRIORITY: MEDIUM
**Goal:** Allow testing/promotional access without payment

**Coupon Types:**
- `free_trial` - Extended free trial (e.g., 90 days)
- `discount` - % off subscription (e.g., 50% off)
- `free_forever` - Permanent free access

**Pre-Created Test Coupons:**
- `DEVTEST` - free_forever, 10 uses, development testing
- `BETA2026` - free_trial 180 days, 100 uses, beta testers
- `PARTNER50` - 50% discount 365 days, 50 uses, partners

---

## Reading Display Thresholds

| Metric   | Green     | Yellow    | Red           |
|----------|-----------|-----------|---------------|
| pH       | 7.2-7.6   | 7.0-7.8   | <7.0 or >7.8  |
| Chlorine | 1.0-3.0   | 0.5-4.0   | <0.5 or >4.0  |
| ORP      | 650-750   | 600-800   | <600 or >800  |

---

## Database Tables Summary

### Pi-Side (SQLite)
```
readings           - Pool chemistry readings (1min intervals)
alarm_events       - Alarm start/end events
maintenance_logs   - User maintenance actions
```

### Server-Side (MySQL)
```
# Existing
pi_devices         - Registered Pi devices
device_health      - Health heartbeats
portal_users       - Customer accounts
user_devices       - User-device links
ai_suggestions     - AI recommendations
ai_responses       - AI Q&A history

# New (Cloud Integration)
device_readings_latest   - Latest reading per device/metric
device_readings_history  - Historical readings for charts
subscription_plans       - Billing tiers
user_subscriptions       - Active subscriptions
payment_history          - Payment records
coupons                  - Promo codes
coupon_redemptions       - Code usage tracking
```

---

## Verification Checklist

### Phase 1-2 Testing (Data Pipeline)
- [ ] Pi uploads every 6 minutes when enabled
- [ ] Upload includes all latest readings
- [ ] Failed uploads are retried on next cycle
- [ ] Upload status shown in Pi settings
- [ ] Server accepts valid API key
- [ ] Server rejects invalid API key
- [ ] Readings stored in database
- [ ] Duplicate uploads handled gracefully

### Phase 3 Testing (Portal Display)
- [ ] Portal shows latest readings
- [ ] "Last updated" time is accurate
- [ ] Color coding matches thresholds
- [ ] Multiple devices display correctly

### Phase 7 Testing (AI)
- [ ] AI suggestions display on portal
- [ ] User can mark suggestions as done
- [ ] AI analysis grades show correctly

### Phase 9-11 Testing (Billing)
- [ ] Stripe checkout works
- [ ] Subscriptions activate after payment
- [ ] Coupons can be redeemed
- [ ] Free trial works
- [ ] Account suspension works

---

## Critical Files Summary

### Pi Software (PoolDash_v6)
| File | Purpose |
|------|---------|
| `scripts/cloud_upload.py` | Upload service (NEW) |
| `scripts/systemd/poolaissistant_upload.*` | Timer service (NEW) |
| `pooldash_app/persist.py` | Upload settings |
| `tools/modbus_logger.py` | Data source (existing) |

### Web Portal (Customer-Facing)
| File | Purpose |
|------|---------|
| `php_deploy/portal/device.php` | Display data + AI panel |
| `php_deploy/portal/billing.php` | Subscription management (NEW) |
| `php_deploy/portal/redeem.php` | Coupon redemption (NEW) |
| `php_deploy/includes/PortalDevices.php` | Data + AI access |
| `php_deploy/includes/Subscription.php` | Billing logic (NEW) |
| `php_deploy/includes/Coupons.php` | Coupon logic (NEW) |

### Web Portal (Admin Backend)
| File | Purpose |
|------|---------|
| `php_deploy/admin/clients.php` | Client management (NEW) |
| `php_deploy/admin/client_detail.php` | Client detail (NEW) |
| `php_deploy/api/device/snapshot.php` | Receive uploads (NEW) |
| `php_deploy/api/webhooks/stripe.php` | Payment webhooks (NEW) |

### Database Migrations
| File | Purpose |
|------|---------|
| `database/schema_readings.sql` | Readings tables |
| `database/schema_billing.sql` | Subscription + payment tables |
| `database/schema_coupons.sql` | Coupon tables |

---

## Progressive Build Order

**Stage 1: Data Pipeline (Phases 1-2)** - Week 1
1. Create `cloud_upload.py` script on Pi
2. Create server `snapshot.php` endpoint
3. Create database tables for readings
4. Test data flows Pi → Server → Database
5. Add upload status to Pi settings UI

**Stage 2: Portal Data Display (Phases 3, 7)** - Week 2
1. Show latest readings on device page with color-coded status
2. Add AI suggestions panel
3. Show AI analysis grades
4. "Last updated X minutes ago" display

**Stage 3: Admin Client Management (Phase 8)** - Week 3
1. Create admin clients list page
2. Create client detail page with device data
3. Add search/filter/pagination
4. Manual suspend/activate actions

**Stage 4: Billing Foundation (Phases 9-10)** - Week 4
1. Set up Stripe account and API keys
2. Create subscription_plans table with tiers
3. Create billing.php portal page
4. Implement Stripe Checkout redirect
5. Handle Stripe webhooks

**Stage 5: Coupon System (Phase 11)** - Week 5
1. Create coupons tables
2. Create admin coupon management
3. Create portal redemption flow
4. Pre-create test coupons

**Stage 6: Charts & History (Phase 4)** - Week 6
1. Create readings API endpoint
2. Integrate Plotly.js for charts
3. Add time range selectors

**Stage 7: Notifications & Polish (Phases 5-6)** - Week 7+
1. Implement email notifications
2. Mobile-responsive design
3. PWA capabilities
