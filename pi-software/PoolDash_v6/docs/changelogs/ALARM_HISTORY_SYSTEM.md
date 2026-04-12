# Alarm History & Log System

**Date**: 2026-01-30
**Status**: ✅ Deployed and Operational

---

## Overview

Created a comprehensive alarm history and logging system that stores all alarm events with acknowledgments, notes, and detailed tracking.

---

## Features

### 1. **Dedicated Alarm Database** ✅
- New SQLite database: `alarm_log.sqlite3`
- Stores complete alarm history with metadata
- Indexed for fast queries
- Separate from live readings database

### 2. **Alarm History Viewer** ✅
- Accessible via button on alarms page
- URL: `http://10.0.30.80:8080/alarms/Main/history`
- Clean, professional interface
- Real-time statistics dashboard

### 3. **Filtering & Search** ✅
Filter alarms by:
- Severity (Critical, Warning, Info)
- Status (Acknowledged / Unacknowledged)
- Date range (since date)
- Pool/Controller

### 4. **Alarm Acknowledgment** ✅
For each alarm:
- Mark as acknowledged
- Add your name
- Record action taken
- Add detailed notes
- Track when acknowledged

### 5. **Statistics Dashboard** ✅
Shows at-a-glance:
- Total alarms logged
- Count by severity (Critical/Warning/Info)
- Acknowledged vs unacknowledged
- Average alarm duration

### 6. **Export to CSV** ✅
- Export filtered results
- Includes all fields
- For reporting and analysis
- Timestamped filename

### 7. **Sync from Events** ✅
- One-click sync from live alarm_events table
- Imports historical data
- Maps alarm codes to human names
- Calculates durations

---

## Database Schema

### alarm_log Table:
```sql
CREATE TABLE alarm_log (
    id INTEGER PRIMARY KEY,
    pool TEXT,
    host TEXT,
    alarm_label TEXT,          -- Technical code
    alarm_name TEXT,            -- Human-readable name
    severity TEXT,              -- critical/warning/info
    started_ts TEXT,
    ended_ts TEXT,
    duration_seconds INTEGER,
    acknowledged BOOLEAN,
    acknowledged_by TEXT,
    acknowledged_ts TEXT,
    notes TEXT,                 -- Operator notes
    action_taken TEXT,          -- What was done
    created_ts TEXT
)
```

### Indexes:
- `idx_alarm_log_pool_ts` - Fast pool queries
- `idx_alarm_log_severity` - Filter by severity
- `idx_alarm_log_ack` - Filter by acknowledgment status

---

## Access & Usage

### Access Alarm History:
1. Navigate to any pool's alarms page:
   - `http://10.0.30.80:8080/alarms/Main`
2. Click **"📋 View Full Alarm History & Log"** button at bottom
3. Opens detailed history page

### Filter Alarms:
- **Severity dropdown**: Select Critical/Warning/Info or All
- **Status dropdown**: Acknowledged/Unacknowledged or All
- **Since Date**: Pick start date for range
- Click **Filter** to apply

### Acknowledge an Alarm:
1. Find alarm in history list
2. Click **View** button
3. Fill in:
   - Your name
   - Action taken (e.g., "Cleaned pH probe")
   - Additional notes
4. Click **Acknowledge**

### Export Data:
1. Apply desired filters
2. Click **📥 Export CSV** button
3. Downloads CSV file with all filtered results

### Sync Historical Data:
1. Click **🔄 Sync from Events** button
2. Imports alarms from alarm_events table
3. Shows count of newly synced alarms

---

## File Structure

### New Files:
```
pooldash_app/
├── db/
│   ├── __init__.py                    (Created)
│   └── alarm_log.py                   (Created)
│
├── blueprints/
│   └── alarms.py                      (Updated with history routes)
│
└── templates/
    ├── alarm_history.html             (Created)
    └── alarms_improved.html           (Updated with history button)
```

### Database Location:
```
/opt/PoolAIssistant/data/alarm_log.sqlite3
```

---

## API Endpoints

### View History Page:
```
GET /alarms/<pool>/history
Query params: severity, acknowledged, since_date
```

### Acknowledge Alarm:
```
POST /alarms/acknowledge/<alarm_id>
Body: {acknowledged_by, action_taken, notes}
```

### Sync from Events:
```
POST /alarms/<pool>/sync
```

### Export CSV:
```
GET /alarms/<pool>/export
Query params: severity, acknowledged, since_date
```

---

## Example Workflow

### Scenario: pH Probe Fault Alarm

1. **Alarm Triggers** (15:50)
   - pH probe stops responding
   - Appears on live alarms page
   - Auto-synced to alarm_log database

2. **Operator Views History** (16:00)
   - Clicks "View Full Alarm History" button
   - Sees alarm in Critical severity section
   - Notes it's been active for 10 minutes

3. **Operator Takes Action** (16:05)
   - Cleans pH probe
   - Recalibrates sensor
   - Alarm clears (16:10)

4. **Operator Acknowledges** (16:15)
   - Opens alarm details
   - Enters name: "John Smith"
   - Action taken: "Cleaned and recalibrated pH probe"
   - Notes: "Probe had mineral buildup. Cleaned with acid wash and recalibrated. Reading now stable at pH 7.4"
   - Clicks Acknowledge

5. **Record Saved**
   - Alarm marked as acknowledged
   - Full audit trail preserved
   - Available for future reference

6. **Generate Report** (End of month)
   - Filter: Last 30 days
   - Export CSV
   - Review alarm patterns
   - Identify if probe cleaning needed more frequently

---

## Benefits

### For Operators:
- ✅ Clear record of all alarms
- ✅ Document actions taken
- ✅ Track response times
- ✅ Easy-to-use interface

### For Management:
- ✅ Full audit trail
- ✅ Performance metrics
- ✅ Identify recurring issues
- ✅ Export for compliance

### For Maintenance:
- ✅ Historical patterns
- ✅ Equipment reliability data
- ✅ Preventive maintenance scheduling
- ✅ Root cause analysis

---

## Statistics Example

```
Total Alarms: 1,247
├─ Critical: 23 (2%)
├─ Warning: 156 (12%)
└─ Info: 1,068 (86%)

Acknowledged: 892 (72%)
Unacknowledged: 355 (28%)

Avg Duration: 12.3 minutes
```

---

## Future Enhancements

Possible additions:
1. **Email/SMS notifications** on critical alarms
2. **Auto-acknowledgment** after alarm clears
3. **Alarm patterns** - detect recurring issues
4. **Maintenance scheduling** based on alarm frequency
5. **Multi-user permissions** - who can acknowledge
6. **Alarm comments/discussion** - team collaboration
7. **Dashboard charts** - alarm trends over time
8. **PDF reports** - formatted alarm summaries
9. **SLA tracking** - response time metrics
10. **Integration** - sync with maintenance logs

---

## Maintenance

### Regular Tasks:

**Monthly**:
- Review unacknowledged alarms
- Export historical data for archival
- Check database size

**Quarterly**:
- Analyze alarm patterns
- Update alarm descriptions if needed
- Train new operators on system

**Database Maintenance**:
```bash
# Check size
ls -lh /opt/PoolAIssistant/data/alarm_log.sqlite3

# Vacuum (compact)
sqlite3 /opt/PoolAIssistant/data/alarm_log.sqlite3 "VACUUM;"

# Backup
cp /opt/PoolAIssistant/data/alarm_log.sqlite3 \
   /opt/PoolAIssistant/data/backups/alarm_log_$(date +%Y%m%d).sqlite3
```

---

## Testing Checklist

- [x] Alarm history page loads
- [x] Button appears on alarms page
- [x] Filtering works (severity, acknowledged, date)
- [x] Statistics display correctly
- [x] Acknowledgment saves properly
- [x] Notes and actions recorded
- [x] CSV export works
- [x] Sync from events imports data
- [x] UI service restarted successfully
- [x] No errors in logs

---

## Summary

**Created**: Comprehensive alarm tracking system
**Database**: Dedicated alarm_log.sqlite3
**Features**: History, filtering, acknowledgment, notes, export
**Access**: Button on alarms page → Full history viewer
**Status**: Deployed and ready to use

**Impact**: Transforms alarms from transient events into documented, actionable records with full audit trails.

---

*Deployed: 2026-01-30*
*Location: http://10.0.30.80:8080/alarms/Main/history*
*Status: Operational*
