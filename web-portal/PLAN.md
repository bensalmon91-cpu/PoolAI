# PoolAIssistant Web Portal

## Executive Summary

Create a customer-facing web portal where account holders can:
1. Register and log in to their account
2. View live pool data from their linked Pi devices
3. Access historical charts and trends
4. Receive alarm notifications
5. Manage their devices and settings remotely

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CUSTOMER WEB PORTAL                                │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │    Login /    │  │   Dashboard   │  │   Historical  │  │   Account    │  │
│  │   Register    │  │  (Live Data)  │  │    Charts     │  │   Settings   │  │
│  └───────────────┘  └───────────────┘  └───────────────┘  └──────────────┘  │
│                                                                              │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │    Alarms     │  │   Device      │  │  Notifications│  │   Reports    │  │
│  │    History    │  │   Management  │  │   Settings    │  │   Export     │  │
│  └───────────────┘  └───────────────┘  └───────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER (PHP)                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │  Auth API     │  │  Readings API │  │  Alarms API   │  │  Device API  │  │
│  │  /api/auth/*  │  │  /api/data/*  │  │  /api/alarms/*│  │  /api/device │  │
│  └───────────────┘  └───────────────┘  └───────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE (MySQL)                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │    users      │  │ user_devices  │  │ cloud_readings│  │ cloud_alarms │  │
│  │ (customers)   │  │   (linking)   │  │ (synced data) │  │  (alerts)    │  │
│  └───────────────┘  └───────────────┘  └───────────────┘  └──────────────┘  │
│                                                                              │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                    │
│  │  pi_devices   │  │ device_health │  │ notifications │                    │
│  │  (existing)   │  │  (existing)   │  │   (new)       │                    │
│  └───────────────┘  └───────────────┘  └───────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │ Data Sync (every 5 min)
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
         ┌────┴────┐            ┌────┴────┐            ┌────┴────┐
         │  Pi 1   │            │  Pi 2   │            │  Pi N   │
         │ Pool A  │            │ Pool B  │            │ Pool N  │
         └─────────┘            └─────────┘            └─────────┘
```

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend Stack | PHP + Vanilla JS (or Vue.js) | Match existing admin panel, no build step needed |
| Authentication | Session-based with PHP | Simple, secure, works with Hostinger |
| Data Sync Frequency | Every 5 minutes | Balance between freshness and server load |
| Data Retention (Cloud) | 90 days | Sufficient for trends, manageable storage |
| Real-time Updates | Polling (30s) | WebSockets complex on shared hosting |
| Multi-device | Yes | One account can have multiple Pi devices |
| Sharing | Optional (Phase 2) | Share read-only access with others |

---

## Database Schema

### New Tables

```sql
-- Customer accounts (separate from admin_users)
CREATE TABLE portal_users (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    company VARCHAR(200),
    phone VARCHAR(30),
    email_verified TINYINT(1) DEFAULT 0,
    email_verify_token VARCHAR(64),
    password_reset_token VARCHAR(64),
    password_reset_expires DATETIME,
    status ENUM('active', 'suspended', 'pending') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,
    settings_json TEXT,  -- notification preferences, timezone, etc.
    INDEX idx_email (email),
    INDEX idx_status (status)
);

-- Link users to their Pi devices
CREATE TABLE user_devices (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    device_id INT UNSIGNED NOT NULL,  -- FK to pi_devices.id
    role ENUM('owner', 'viewer', 'manager') DEFAULT 'owner',
    nickname VARCHAR(100),  -- User-friendly name for the device
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    link_code VARCHAR(20),  -- Used during device linking process
    link_code_expires DATETIME,
    UNIQUE KEY unique_user_device (user_id, device_id),
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_device (device_id)
);

-- Pool readings synced from Pi devices (aggregated/sampled)
CREATE TABLE cloud_readings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL,
    recorded_at DATETIME NOT NULL,  -- Original timestamp from Pi
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Common readings (nullable - not all controllers have all)
    ph DECIMAL(4,2),
    chlorine DECIMAL(5,2),
    orp INT,
    temperature DECIMAL(4,1),

    -- Additional readings stored as JSON for flexibility
    extra_json TEXT,  -- {"conductivity": 1200, "flow_rate": 45, ...}

    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    INDEX idx_device_pool_time (device_id, pool, recorded_at),
    INDEX idx_recorded (recorded_at)
);

-- Alarms synced from Pi devices
CREATE TABLE cloud_alarms (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    device_id INT UNSIGNED NOT NULL,
    pool VARCHAR(100) NOT NULL,
    alarm_code VARCHAR(50),
    alarm_label VARCHAR(200),
    severity ENUM('info', 'warning', 'critical') DEFAULT 'warning',
    started_at DATETIME NOT NULL,
    cleared_at DATETIME,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_by INT UNSIGNED,  -- user who acknowledged
    acknowledged_at DATETIME,
    notes TEXT,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE CASCADE,
    FOREIGN KEY (acknowledged_by) REFERENCES portal_users(id) ON DELETE SET NULL,
    INDEX idx_device_active (device_id, cleared_at),
    INDEX idx_started (started_at)
);

-- Notification preferences and history
CREATE TABLE notifications (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    device_id INT UNSIGNED,
    type ENUM('alarm', 'offline', 'report', 'system') NOT NULL,
    channel ENUM('email', 'push', 'sms') NOT NULL,
    subject VARCHAR(200),
    body TEXT,
    status ENUM('pending', 'sent', 'failed', 'read') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME,
    read_at DATETIME,
    error_message TEXT,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES pi_devices(id) ON DELETE SET NULL,
    INDEX idx_user_status (user_id, status),
    INDEX idx_created (created_at)
);

-- User sessions for portal
CREATE TABLE portal_sessions (
    id VARCHAR(64) PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at)
);

-- Audit log for security
CREATE TABLE portal_audit_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED,
    action VARCHAR(50) NOT NULL,  -- login, logout, device_link, settings_change, etc.
    details_json TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at)
);
```

### Modifications to Existing Tables

```sql
-- Add linking support to pi_devices
ALTER TABLE pi_devices ADD COLUMN link_code VARCHAR(20);
ALTER TABLE pi_devices ADD COLUMN link_code_expires DATETIME;
ALTER TABLE pi_devices ADD COLUMN cloud_sync_enabled TINYINT(1) DEFAULT 1;
ALTER TABLE pi_devices ADD COLUMN last_reading_sync DATETIME;
```

---

## Data Sync Strategy

### From Pi to Cloud

The Pi's `health_reporter.py` will be extended to sync readings:

```
Pi Device                           Cloud Server
    │                                    │
    │ ──── Heartbeat (every 15 min) ───► │  (existing)
    │      + device health               │
    │                                    │
    │ ──── Reading Sync (every 5 min) ─► │  (new)
    │      + sampled readings            │
    │      + active alarms               │
    │                                    │
    │ ◄─── Sync Response ─────────────── │
    │      + commands                    │
    │      + AI questions (existing)     │
    │                                    │
```

### Data Sampling Strategy

To avoid overwhelming the server, readings are sampled:

| Data Type | Local (Pi) | Cloud Sync |
|-----------|------------|------------|
| Readings | Every 30s | Every 5 min (latest value) |
| Hourly averages | Calculated | Synced daily |
| Alarms | Real-time | Within 1 min of change |
| Device health | Continuous | Every 15 min |

### Sync Payload (Pi → Cloud)

```json
{
  "device_id": "abc123",
  "api_key": "xxx",
  "timestamp": "2026-03-14T10:30:00Z",
  "readings": [
    {
      "pool": "Main Pool",
      "recorded_at": "2026-03-14T10:30:00Z",
      "ph": 7.4,
      "chlorine": 1.2,
      "orp": 720,
      "temperature": 28.5,
      "extra": {"conductivity": 1200}
    }
  ],
  "alarms": [
    {
      "pool": "Main Pool",
      "code": "PH_HIGH",
      "label": "pH High Alarm",
      "severity": "warning",
      "started_at": "2026-03-14T09:15:00Z",
      "cleared_at": null
    }
  ]
}
```

---

## API Endpoints

### Authentication

```
POST /api/portal/auth/register
  Body: {email, password, name, company}
  Response: {ok: true, message: "Verification email sent"}

POST /api/portal/auth/login
  Body: {email, password, remember_me}
  Response: {ok: true, user: {...}, session_token: "xxx"}

POST /api/portal/auth/logout
  Headers: Authorization: Bearer <token>
  Response: {ok: true}

POST /api/portal/auth/forgot-password
  Body: {email}
  Response: {ok: true, message: "Reset email sent"}

POST /api/portal/auth/reset-password
  Body: {token, new_password}
  Response: {ok: true}

GET /api/portal/auth/verify-email?token=xxx
  Response: Redirect to login with success message
```

### Device Management

```
GET /api/portal/devices
  Headers: Authorization: Bearer <token>
  Response: {ok: true, devices: [{id, nickname, alias, status, last_seen, pools: [...]}]}

POST /api/portal/devices/link
  Headers: Authorization: Bearer <token>
  Body: {link_code: "ABC123"}
  Response: {ok: true, device: {...}}

DELETE /api/portal/devices/{device_id}
  Headers: Authorization: Bearer <token>
  Response: {ok: true}

PUT /api/portal/devices/{device_id}
  Headers: Authorization: Bearer <token>
  Body: {nickname: "My Pool"}
  Response: {ok: true}

POST /api/portal/devices/{device_id}/generate-link-code
  Headers: Authorization: Bearer <token>
  Response: {ok: true, link_code: "ABC123", expires_at: "..."}
```

### Readings & Data

```
GET /api/portal/devices/{device_id}/live
  Headers: Authorization: Bearer <token>
  Response: {ok: true, pools: [{name, readings: {ph, chlorine, ...}, updated_at}]}

GET /api/portal/devices/{device_id}/readings
  Headers: Authorization: Bearer <token>
  Query: ?pool=Main&from=2026-03-01&to=2026-03-14&interval=hourly
  Response: {ok: true, readings: [{recorded_at, ph, chlorine, ...}]}

GET /api/portal/devices/{device_id}/alarms
  Headers: Authorization: Bearer <token>
  Query: ?status=active|all&from=&to=
  Response: {ok: true, alarms: [{id, pool, label, severity, started_at, cleared_at}]}

POST /api/portal/alarms/{alarm_id}/acknowledge
  Headers: Authorization: Bearer <token>
  Body: {notes: "Checked probe"}
  Response: {ok: true}
```

### User Settings

```
GET /api/portal/user/settings
  Response: {ok: true, settings: {notifications: {...}, timezone, units}}

PUT /api/portal/user/settings
  Body: {notifications: {email_alarms: true, ...}, timezone: "Europe/London"}
  Response: {ok: true}

PUT /api/portal/user/profile
  Body: {name, company, phone}
  Response: {ok: true}

PUT /api/portal/user/password
  Body: {current_password, new_password}
  Response: {ok: true}
```

### Data Sync (Pi → Cloud)

```
POST /api/sync/readings
  Headers: X-API-Key: <device_api_key>
  Body: {readings: [...], alarms: [...]}
  Response: {ok: true, commands: [...]}
```

---

## Frontend Pages

### Page Structure

```
/portal/
├── login                 # Login form
├── register              # Registration form
├── forgot-password       # Password reset request
├── reset-password        # Password reset form
├── verify-email          # Email verification landing
│
├── dashboard             # Main dashboard (after login)
│   ├── /                 # Overview of all devices
│   └── /device/{id}      # Single device detail view
│
├── device/{id}/
│   ├── live              # Live readings view
│   ├── charts            # Historical charts
│   ├── alarms            # Alarm history
│   └── settings          # Device-specific settings
│
├── account/
│   ├── profile           # Edit name, company, etc.
│   ├── security          # Change password, 2FA
│   ├── notifications     # Email/push preferences
│   └── devices           # Manage linked devices
│
└── reports/
    ├── daily             # Daily summary reports
    └── export            # CSV/PDF export
```

### Dashboard Wireframe

```
┌─────────────────────────────────────────────────────────────────┐
│  PoolAIssistant                              [User ▼] [Logout]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  📍 Leisure Centre Pool           Online ● 2 min ago       │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │ │
│  │  │ pH      │ │ Chlorine│ │ ORP     │ │ Temp    │           │ │
│  │  │  7.4    │ │  1.2    │ │  720    │ │  28°C   │           │ │
│  │  │   ✓     │ │   ✓     │ │   ✓     │ │   ✓     │           │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │ │
│  │  ⚠ 1 Active Alarm: pH High (Main Pool)          [View →]   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  📍 Hotel Spa                      Online ● 5 min ago      │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │ │
│  │  │ pH      │ │ Chlorine│ │ ORP     │ │ Temp    │           │ │
│  │  │  7.2    │ │  1.5    │ │  750    │ │  38°C   │           │ │
│  │  │   ✓     │ │   ✓     │ │   ✓     │ │   ✓     │           │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │ │
│  │  ✓ No active alarms                             [View →]   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  [+ Link New Device]                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Device Linking Flow

How a user connects their Pi to their portal account:

```
┌─────────────┐                              ┌─────────────┐
│   Pi Device │                              │ Web Portal  │
└──────┬──────┘                              └──────┬──────┘
       │                                            │
       │  1. User clicks "Link to Portal"           │
       │     in Pi Settings page                    │
       │                                            │
       │  2. Pi requests link code from server      │
       │ ─────────────────────────────────────────► │
       │                                            │
       │  3. Server returns 6-digit code            │
       │ ◄───────────────────────────────────────── │
       │     (valid for 15 minutes)                 │
       │                                            │
       │  4. Pi displays code on screen:            │
       │     "Enter this code in your portal:       │
       │      ABC-123"                              │
       │                                            │
       │                                            │  5. User logs into portal
       │                                            │     clicks "Link Device"
       │                                            │     enters "ABC-123"
       │                                            │
       │  6. Server validates code, creates link    │
       │                                            │
       │  7. Pi receives confirmation on            │
       │     next heartbeat                         │
       │ ◄───────────────────────────────────────── │
       │                                            │
       │  8. Pi shows "Device linked to             │
       │     user@example.com"                      │
       │                                            │
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
**Goal:** Basic auth and device linking

- [ ] Database schema migration
- [ ] User registration & login
- [ ] Email verification
- [ ] Password reset flow
- [ ] Session management
- [ ] Device linking (code-based)
- [ ] Basic dashboard (list devices)

### Phase 2: Live Data (Week 3-4)
**Goal:** View real-time readings

- [ ] Extend Pi health_reporter for reading sync
- [ ] Cloud readings API endpoint
- [ ] Live dashboard with polling
- [ ] Device detail page
- [ ] Pool readings display
- [ ] Connection status indicators

### Phase 3: Historical Data (Week 5-6)
**Goal:** Charts and trends

- [ ] Historical readings API
- [ ] Plotly.js charts integration
- [ ] Date range selector
- [ ] Data aggregation (hourly/daily)
- [ ] Export to CSV

### Phase 4: Alarms (Week 7-8)
**Goal:** Alarm visibility and notifications

- [ ] Alarm sync from Pi
- [ ] Active alarms display
- [ ] Alarm history
- [ ] Alarm acknowledgment
- [ ] Email notifications (critical alarms)

### Phase 5: Polish (Week 9-10)
**Goal:** User experience refinement

- [ ] Mobile-responsive design
- [ ] Notification preferences
- [ ] Account settings
- [ ] Multi-device dashboard
- [ ] Performance optimization
- [ ] Security audit

### Phase 6: Advanced (Future)
**Goal:** Additional features

- [ ] Push notifications (PWA)
- [ ] Device sharing (read-only access)
- [ ] Automated reports (daily/weekly email)
- [ ] PDF report generation
- [ ] SMS alerts (premium)
- [ ] API access for integrations

---

## Security Considerations

### Authentication
- Passwords hashed with bcrypt (cost 12)
- Session tokens: 256-bit random, HTTPOnly cookies
- CSRF protection on all forms
- Rate limiting on login (5 attempts per 15 min)
- Account lockout after 10 failed attempts

### Authorization
- Users can only see their linked devices
- Device linking requires valid code
- API keys are device-specific, not user-specific
- Role-based access (owner/viewer/manager)

### Data Protection
- HTTPS everywhere
- No sensitive data in URLs
- Audit logging for account actions
- Data encrypted at rest (MySQL)
- Session expiry (7 days inactive, 30 days max)

### Pi Security
- Device API key required for sync
- Rate limiting on sync endpoints
- Payload validation and sanitization

---

## File Structure

```
public_html/poolaissistant/
├── portal/                      # Customer portal (new)
│   ├── index.php               # Entry point / router
│   ├── assets/
│   │   ├── css/
│   │   │   └── portal.css
│   │   └── js/
│   │       ├── dashboard.js
│   │       ├── charts.js
│   │       └── auth.js
│   ├── pages/
│   │   ├── login.php
│   │   ├── register.php
│   │   ├── dashboard.php
│   │   ├── device.php
│   │   ├── charts.php
│   │   ├── alarms.php
│   │   └── account.php
│   └── includes/
│       ├── header.php
│       ├── footer.php
│       └── nav.php
│
├── api/
│   └── portal/                 # Portal API endpoints (new)
│       ├── auth/
│       │   ├── login.php
│       │   ├── register.php
│       │   ├── logout.php
│       │   └── reset-password.php
│       ├── devices/
│       │   ├── list.php
│       │   ├── link.php
│       │   └── readings.php
│       ├── alarms/
│       │   ├── list.php
│       │   └── acknowledge.php
│       └── user/
│           ├── settings.php
│           └── profile.php
│
├── includes/
│   ├── portal_auth.php         # Portal authentication (new)
│   └── portal_helpers.php      # Portal utilities (new)
│
└── config/
    └── portal.php              # Portal configuration (new)
```

---

## Pi-Side Changes

### New: Cloud Sync in health_reporter.py

```python
def sync_readings_to_cloud():
    """Sync recent readings to cloud portal."""
    if not settings.get('cloud_sync_enabled', True):
        return

    # Get latest reading per pool
    readings = get_latest_readings()

    # Get active alarms
    alarms = get_active_alarms()

    # Send to cloud
    response = requests.post(
        f"{BACKEND_URL}/api/sync/readings",
        headers={"X-API-Key": api_key},
        json={
            "readings": readings,
            "alarms": alarms
        },
        timeout=10
    )

    if response.ok:
        update_last_sync_time()
```

### New: Link Code Generation in Settings Page

Add to settings.html:
- "Link to Portal" button
- Display 6-digit code when generated
- Show linked account email when linked

---

## Cost Considerations

### Hostinger Resources
- Database: Additional tables, moderate growth
- Storage: ~1KB per device per day (readings)
- Bandwidth: Minimal (API calls only)

### Estimated Storage (per device per year)
- Readings (5-min intervals): ~100K rows = ~10MB
- Alarms: ~1K rows = ~100KB
- Total: ~10MB per device per year

### For 100 devices
- ~1GB storage per year
- Well within Hostinger limits

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Registration → Active | > 60% |
| Daily active users | > 30% of registered |
| Device link success | > 95% |
| Page load time | < 2 seconds |
| Data freshness | < 5 minutes |
| Uptime | > 99.5% |

---

## Open Questions

1. **Pricing model**: Free tier vs paid features?
2. **Device limits**: Max devices per account?
3. **Data export**: Full history or limited?
4. **White-labeling**: Custom branding for resellers?
5. **Mobile app**: PWA sufficient or native needed?

---

## Next Steps

1. Review and approve this plan
2. Create database migration script
3. Implement Phase 1 (auth + device linking)
4. Test with a single Pi device
5. Iterate based on feedback

---

*Plan created: March 2026*
*Last updated: March 2026*
