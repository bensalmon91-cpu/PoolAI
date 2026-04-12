# PoolAIssistant Software Update Guide

## Overview

The software update system allows you to push new versions of the Pi app to all devices automatically.

**Flow:**
1. Package Pi code into a `.tar.gz` file
2. Upload to admin panel with version number
3. Pi checks daily at 3 AM (or manually triggered)
4. Pi downloads, verifies, extracts, and restarts

---

## Step 1: Package the Update

### Option A: PowerShell Script (Windows)

```powershell
cd "C:\Users\bensa\iCloudDrive\MBSoftware\PoolAIssitant v6.1.1\PoolDash_v6"
.\tools\package_update.ps1
```

Or specify version:
```powershell
.\tools\package_update.ps1 -Version 6.2.1
```

This creates: `releases\update-v6.2.1.tar.gz`

### Option B: Manual Packaging

From the `PoolDash_v6` folder:

```bash
# Create tar.gz with these folders/files:
tar -czvf update-v6.2.1.tar.gz \
    pooldash_app \
    scripts \
    docs \
    VERSION \
    requirements.txt
```

**What's included:**
- `pooldash_app/` - Flask web app (blueprints, templates, static)
- `scripts/` - All automation scripts (chunk_manager, watchdog, etc.)
- `docs/` - Documentation
- `VERSION` - Version file (must match what you upload)
- `requirements.txt` - Python dependencies

**What's NOT included:**
- `instance/` - Local Flask instance data
- `*.sqlite3` - Database files
- `__pycache__/` - Python cache
- `.env` - Environment files
- `tools/` - Packaging tools
- `releases/` - Previous packages

---

## Step 2: Upload to Server

1. **Go to:** https://poolaissistant.modprojects.co.uk/admin/updates.php

2. **Fill in the form:**
   - **Version:** `6.2.1` (must match VERSION file, semver format)
   - **Description:** What's new in this version
   - **File:** Select your `update-v6.2.1.tar.gz`

3. **Click "Upload Update"**

4. **Verify:** The update appears in the list with:
   - ✅ Active status
   - Correct file size
   - SHA256 checksum

---

## Step 3: Pi Downloads and Installs

### Automatic (Default)

The Pi checks for updates daily at **3:00 AM** via `update_check.timer`.

If an update is found:
1. Downloads the package
2. Verifies SHA256 checksum
3. Extracts to `/opt/PoolAIssistant/app/`
4. Creates backup of old version
5. Restarts services

### Manual Trigger

SSH into Pi and run:
```bash
sudo python3 /opt/PoolAIssistant/app/scripts/update_check.py --apply
sudo systemctl restart poolaissistant_ui poolaissistant_logger
```

Or just check status:
```bash
python3 /opt/PoolAIssistant/app/scripts/update_check.py --status
```

---

## Server File Structure

```
mod-projects-website/
├── api/updates/
│   ├── check.php      # Pi calls this to check for updates
│   └── download.php   # Pi downloads from here
├── data/updates/
│   ├── .htaccess      # Protects direct access
│   └── update-v6.2.1.tar.gz  # Your uploaded packages
└── admin/updates.php  # Admin upload interface
```

---

## Pi File Structure (After Update)

```
/opt/PoolAIssistant/
├── app/                      # ← Updated files go here
│   ├── pooldash_app/
│   ├── scripts/
│   ├── docs/
│   └── VERSION
├── data/                     # ← NOT touched by updates
│   ├── pool_readings.sqlite3
│   ├── pooldash_settings.json
│   └── chunks/
└── app_backup/               # ← Previous version backup
```

---

## Version Numbering

Use **semantic versioning**: `MAJOR.MINOR.PATCH`

- **MAJOR:** Breaking changes
- **MINOR:** New features (backwards compatible)
- **PATCH:** Bug fixes

Examples:
- `6.1.1` → `6.1.2` (bug fix)
- `6.1.2` → `6.2.0` (new feature)
- `6.2.0` → `7.0.0` (breaking change)

The Pi only updates if server version > current version.

---

## Rollback

If an update fails verification, it automatically rolls back to the previous version.

Manual rollback:
```bash
# On Pi
cd /opt/PoolAIssistant
sudo rm -rf app
sudo mv app_backup app
sudo systemctl restart poolaissistant_ui poolaissistant_logger
```

---

## Troubleshooting

### Update not appearing on Pi

Check the update status:
```bash
python3 /opt/PoolAIssistant/app/scripts/update_check.py --status
```

Check settings have API key:
```bash
cat /opt/PoolAIssistant/data/pooldash_settings.json | grep api_key
```

### Download fails

Check Pi can reach server:
```bash
curl -I https://poolaissistant.modprojects.co.uk/api/updates/check.php
```

### Checksum mismatch

Re-upload the package. May have been corrupted during upload.

### Services won't restart

Check logs:
```bash
sudo journalctl -u poolaissistant_ui -n 50
```
