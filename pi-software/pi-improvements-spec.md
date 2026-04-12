# PoolDash Pi Reliability Improvements Specification

## Current Issues

- Pi running continuously since 2025 without reboot
- 5.9GB SQLite database on SD card with constant writes
- 45% swap usage indicating memory pressure
- SD card wear from frequent database I/O

---

## 1. Move Database to USB SSD

**Priority:** High
**Impact:** Significantly extends system lifespan and improves performance

### Hardware
- USB 3.0 SSD (128GB minimum, 256GB recommended)
- Powered USB hub if using multiple USB devices

### Implementation
1. Format SSD as ext4
2. Mount at `/mnt/ssd` with appropriate fstab entry
3. Migrate database files to SSD
4. Update PoolDash configuration to use new paths
5. Keep SD card for OS only (read-mostly operations)

### fstab Example
```
UUID=<ssd-uuid>  /mnt/ssd  ext4  defaults,noatime  0  2
```

---

## 2. SQLite Database Maintenance

**Priority:** High
**Impact:** Prevents database bloat and improves query performance

### VACUUM Schedule
Create `/home/mbs/pooldash/maintenance/vacuum_db.sh`:
```bash
#!/bin/bash
# Stop the logger temporarily
sudo systemctl stop pooldash-logger

# Vacuum the database
sqlite3 /mnt/ssd/pooldash/pool_readings.sqlite3 "VACUUM;"
sqlite3 /mnt/ssd/pooldash/maintenance_logs.sqlite3 "VACUUM;"

# Restart the logger
sudo systemctl start pooldash-logger
```

### Cron Entry (weekly, Sunday 3am)
```
0 3 * * 0 /home/mbs/pooldash/maintenance/vacuum_db.sh >> /var/log/pooldash-vacuum.log 2>&1
```

---

## 3. Database Archiving Strategy

**Priority:** Medium
**Impact:** Keeps active database size manageable

### Approach
- Archive readings older than 6 months to separate database files
- Keep active database lean for better performance
- Store archives on SSD or external backup location

### Archive Script (`archive_old_readings.sh`)
```bash
#!/bin/bash
ARCHIVE_DATE=$(date -d "6 months ago" +%Y-%m-%d)
ARCHIVE_FILE="/mnt/ssd/pooldash/archives/readings_before_${ARCHIVE_DATE}.sqlite3"

sqlite3 /mnt/ssd/pooldash/pool_readings.sqlite3 <<EOF
ATTACH DATABASE '${ARCHIVE_FILE}' AS archive;
CREATE TABLE IF NOT EXISTS archive.readings AS SELECT * FROM readings WHERE timestamp < '${ARCHIVE_DATE}';
DELETE FROM readings WHERE timestamp < '${ARCHIVE_DATE}';
DETACH DATABASE archive;
VACUUM;
EOF
```

### Cron Entry (monthly, 1st of month at 4am)
```
0 4 1 * * /home/mbs/pooldash/maintenance/archive_old_readings.sh >> /var/log/pooldash-archive.log 2>&1
```

---

## 4. Scheduled Reboots

**Priority:** Medium
**Impact:** Clears memory fragmentation, resets system state

### Cron Entry (weekly, Sunday 4am after maintenance)
```
0 4 * * 0 /sbin/shutdown -r now
```

### Alternative: Systemd Timer
Create `/etc/systemd/system/weekly-reboot.timer`:
```ini
[Unit]
Description=Weekly Reboot

[Timer]
OnCalendar=Sun 04:00
Persistent=true

[Install]
WantedBy=timers.target
```

---

## 5. Memory Management

**Priority:** Medium
**Impact:** Reduces swap usage and improves responsiveness

### Increase Swap (if staying on SD)
```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile  # Set CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### Move Swap to SSD
```bash
sudo fallocate -l 1G /mnt/ssd/swapfile
sudo chmod 600 /mnt/ssd/swapfile
sudo mkswap /mnt/ssd/swapfile
# Add to fstab: /mnt/ssd/swapfile none swap sw 0 0
```

### Reduce Chromium Memory
Consider using a lighter kiosk browser or adding Chromium flags:
```
--disable-extensions
--disable-plugins
--disable-background-networking
--memory-pressure-off
```

---

## 6. Log Rotation

**Priority:** Low
**Impact:** Prevents disk fill from log accumulation

### Logrotate Config (`/etc/logrotate.d/pooldash`)
```
/var/log/pooldash*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## 7. Monitoring & Alerts

**Priority:** Low
**Impact:** Early warning of issues

### Simple Health Check Script (`/home/mbs/pooldash/maintenance/health_check.sh`)
```bash
#!/bin/bash
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
MEM_AVAIL=$(free -m | awk '/Mem:/ {print $7}')
DB_SIZE=$(du -m /mnt/ssd/pooldash/pool_readings.sqlite3 | cut -f1)

if [ "$DISK_USAGE" -gt 85 ]; then
    echo "WARNING: Disk usage at ${DISK_USAGE}%"
fi

if [ "$MEM_AVAIL" -lt 500 ]; then
    echo "WARNING: Available memory low (${MEM_AVAIL}MB)"
fi

if [ "$DB_SIZE" -gt 10000 ]; then
    echo "WARNING: Database size ${DB_SIZE}MB - consider archiving"
fi
```

### Cron Entry (daily)
```
0 8 * * * /home/mbs/pooldash/maintenance/health_check.sh | mail -s "PoolDash Health Check" admin@example.com
```

---

## Implementation Order

1. **Immediate:** Set up weekly reboot cron job
2. **Short-term:** Purchase and configure USB SSD, migrate database
3. **Short-term:** Implement VACUUM script and cron
4. **Medium-term:** Set up database archiving
5. **Ongoing:** Configure monitoring/alerts

---

## Hardware Recommendations

| Item | Specification | Estimated Cost |
|------|---------------|----------------|
| USB SSD | 256GB USB 3.0 (Samsung T7 or similar) | $40-60 |
| Powered USB Hub | Optional, if power issues | $15-25 |

---

## Backup Strategy

- Continue periodic backups to this OneDrive folder
- Consider automated daily backup of database to network share
- Keep at least 2 weeks of backups before rotation
