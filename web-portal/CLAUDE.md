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

  WARNING: FTP is chrooted to customer portal directory, NOT public_html!
  FTP root maps to: /home/u931726538/domains/poolai.modprojects.co.uk/

=== ACTUAL SERVER PATHS (IMPORTANT!) ===
  Admin backend (poolaissistant.modprojects.co.uk):
    /home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/

  Customer portal (poolai.modprojects.co.uk):
    /home/u931726538/domains/poolai.modprojects.co.uk/

  NOTE: There is also /home/u931726538/public_html/poolaissistant/ but this
        is NOT served by poolaissistant.modprojects.co.uk - don't use it!

=== ADMIN BACKEND ===
URL: https://poolaissistant.modprojects.co.uk
Admin Panel: https://poolaissistant.modprojects.co.uk/admin/

=== CUSTOMER PORTAL ===
URL: https://poolai.modprojects.co.uk

=== SHARED DATABASE (MySQL) ===
Host: localhost
Name: u931726538_PoolAIssistant
User: u931726538_mbs_modproject
Pass: PoolAI2026!

Bootstrap Secret (for device provisioning):
  e1d6eeeb68c011b8c40d8d3386018137be53342a1af7c4d9
```

### Server Paths

**Admin Backend (poolaissistant.modprojects.co.uk):**
```
API:      /api/                    # Device API endpoints
Config:   /config/                 # database.php, config.php
Admin:    /admin/                  # Admin dashboard
Updates:  /data/updates/           # Software update packages (.tar.gz)
```

**Customer Portal (poolai.modprojects.co.uk):**
```
/                    # Root - redirects to login or dashboard
/login.php           # Login page
/dashboard.php       # Device list
/device.php?id=X     # Device detail view
/account.php         # Account settings
```

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

### Data Sync (from Pi)
```
POST /api/sync.php
Headers: Authorization: Bearer <api_key>
Body: { "readings": [...], "alarms": [...] }
```

---

## Database Tables

### software_updates
```sql
CREATE TABLE software_updates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  version VARCHAR(20) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  file_size INT NOT NULL,
  checksum VARCHAR(64) NOT NULL,
  description TEXT,
  is_active TINYINT(1) DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### devices
```sql
CREATE TABLE devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(64) UNIQUE NOT NULL,
  api_key_hash VARCHAR(64) NOT NULL,
  hostname VARCHAR(255),
  model VARCHAR(100),
  software_version VARCHAR(20),
  last_seen TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Deploying Software Updates

### IMPORTANT: FTP Limitations
The FTP account is chrooted to the customer portal directory, NOT the admin backend.
Direct FTP upload to poolaissistant paths will FAIL. Use PHP installer scripts instead.

### From Windows (PoolDash_v6 directory)
```powershell
# 1. Create update package
tar -czvf ../update-v6.4.0.tar.gz --exclude="__pycache__" --exclude="*.pyc" --exclude="instance" --exclude=".git" --exclude="*.sqlite3" --exclude="docs" .

# 2. Get checksum and size
certutil -hashfile ../update-v6.4.0.tar.gz SHA256
(Get-Item ../update-v6.4.0.tar.gz).Length

# 3. Upload to FTP root (customer portal) - this is where FTP has access
curl --ftp-ssl -k -T ../update-v6.4.0.tar.gz -u "u931726538.mbs:Henley2026!" "ftp://ftp.modprojects.co.uk/"

# 4. Create installer script to copy to correct location (see below)
# 5. Upload and run installer via customer portal URL
```

### Installer Script Template (deploy_update.php)
Upload this to FTP root, then access via https://poolai.modprojects.co.uk/deploy_update.php
```php
<?php
// Copy update file from FTP root to correct poolaissistant location
$src = __DIR__ . '/update-v6.4.0.tar.gz';
$dest_dir = '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/data/updates/';
$dest = $dest_dir . 'update-v6.4.0.tar.gz';

if (!is_dir($dest_dir)) mkdir($dest_dir, 0755, true);

if (copy($src, $dest)) {
    echo "SUCCESS: Copied to $dest\n";
    echo "Size: " . filesize($dest) . " bytes\n";

    // Add to database
    require_once '/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/config/database.php';
    $pdo = db();
    $stmt = $pdo->prepare("INSERT INTO software_updates
        (version, filename, file_size, checksum, description, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, NOW())
        ON DUPLICATE KEY UPDATE file_size=?, checksum=?, description=?, is_active=1");
    $stmt->execute(['6.4.0', 'update-v6.4.0.tar.gz', filesize($dest), 'CHECKSUM', 'Description',
                    filesize($dest), 'CHECKSUM', 'Description']);
    echo "Database updated\n";

    // Clean up
    unlink($src);
    unlink(__FILE__);
} else {
    echo "FAILED\n";
}
```

---

## Project Structure

```
web-portal/
├── CLAUDE.md              # This file
├── php_deploy/            # Admin backend (poolaissistant.modprojects.co.uk)
│   ├── api/               # Device API endpoints
│   │   ├── provision.php  # Device registration
│   │   ├── heartbeat.php  # Device heartbeat & AI sync
│   │   └── updates/       # Software update endpoints
│   ├── config/
│   │   ├── config.php     # Constants (bootstrap_secret)
│   │   └── database.php   # PDO connection
│   ├── includes/
│   │   ├── auth.php       # API key validation
│   │   └── api_helpers.php
│   └── admin/             # Admin dashboard
│       ├── ai_dashboard.php
│       ├── ai_questions.php
│       ├── ai_responses.php
│       ├── ai_suggestions.php
│       └── ai_analytics.php
├── poolai_deploy/         # Customer portal (poolai.modprojects.co.uk)
│   ├── index.php          # Smart redirect (login/dashboard)
│   ├── login.php
│   ├── dashboard.php
│   ├── device.php         # Device detail with health/AI data
│   ├── account.php
│   ├── config/
│   │   ├── portal.php     # Portal settings
│   │   └── database.php   # Shared DB connection
│   ├── includes/
│   │   ├── PortalAuth.php
│   │   └── PortalDevices.php
│   └── assets/css/portal.css
└── backend/               # LEGACY: Node.js/Postgres version
```

---

## Common Tasks

### Check if device is provisioned
```sql
SELECT * FROM devices WHERE device_id = 'pi-xxxx-xxxx';
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
SELECT device_id, hostname, software_version, last_seen
FROM devices
ORDER BY last_seen DESC;
```

---

## Important Notes

1. **SERVER PATHS ARE CONFUSING** - There are multiple poolaissistant directories:
   - CORRECT: `/home/u931726538/domains/modprojects.co.uk/public_html/poolaissistant/`
   - WRONG: `/home/u931726538/public_html/poolaissistant/` (exists but NOT served!)
   Always use PHP installer scripts from poolai to deploy to the correct location.

2. **FTP is limited** - The FTP user is chrooted to the customer portal, not admin backend.
   Use installer scripts uploaded to poolai.modprojects.co.uk to copy files to poolaissistant.

3. **Bootstrap secret is hardcoded** on both server and Pi (persist.py DEFAULTS)

4. **Auto-update runs at 3 AM** on Pi devices via systemd timer

5. **Version comparison is semantic** - 6.4.0 > 6.3.0 > 6.2.5

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
