# PoolAIssistant v6.1.1 - Testing Guide

## Pre-Deployment Testing (On PC)

Before deploying to the Raspberry Pi, test everything on your development PC.

### 1. Install Dependencies

```bash
# Navigate to project directory
cd "C:\Users\bensa\iCloudDrive\MBSoftware\PoolAIssitant v6.1.1\PoolDash_v6"

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Linux/Mac:
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 2. Test Modbus Connection

```bash
python test_modbus_connection.py
```

**Expected Output:**
```
============================================================
PoolAIssistant - Modbus Connection Test
============================================================

Found 1 enabled controller(s)

[Pool 1]
Testing 10.0.30.80:502 (unit 1)...
  ✓ Connected successfully
  ✓ Modbus communication OK

============================================================
Summary:
============================================================
  Pool 1: ✓ OK

✓ All controllers reachable
```

**If it fails:**
- Check controller IP address in `instance/pooldash_settings.json`
- Verify controller is powered on and network is accessible
- Check firewall allows port 502
- Try pinging the controller: `ping 10.0.30.80`

### 3. Test Database Logger

**Terminal 1 - Start Logger:**
```bash
python modbus_logger.py
```

**Expected Output:**
```
2026-01-30T10:30:00Z INFO DB ready at ./pool_readings.sqlite3
2026-01-30T10:30:00Z INFO Polling 1 pools every 5.0s
2026-01-30T10:30:05Z INFO [Pool 1 10.0.30.80] wrote 15 readings meta='Ezetrol MK2'
2026-01-30T10:30:10Z INFO [Pool 1 10.0.30.80] wrote 15 readings meta='Ezetrol MK2'
...
```

**What to check:**
- No error messages in logs
- "wrote N readings" appears every 5 seconds (or your configured interval)
- Database file created: `pool_readings.sqlite3`

**Stop the logger:** Press `Ctrl+C`

### 4. Verify Database Contents

```bash
# On Windows (if sqlite3 is in PATH):
sqlite3 pool_readings.sqlite3

# On Linux/Mac:
sqlite3 pool_readings.sqlite3
```

**SQL Commands to test:**
```sql
-- Check tables exist
.tables

-- Should show: alarm_events  device_meta  readings

-- Check readings table
SELECT COUNT(*) FROM readings;
-- Should show rows (number depends on how long logger ran)

-- Check recent readings
SELECT ts, pool, point_label, value
FROM readings
ORDER BY ts DESC
LIMIT 10;

-- Check alarm_events table exists
SELECT COUNT(*) FROM alarm_events;

-- Exit
.quit
```

### 5. Test Web UI

**Terminal 1 - Logger (keep running):**
```bash
python modbus_logger.py
```

**Terminal 2 - Web UI:**
```bash
python run_ui.py
```

**Expected Output:**
```
 * Serving Flask app 'pooldash_app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:8080
 * Running on http://192.168.1.xxx:8080
```

**Open Browser:**
- Navigate to: `http://localhost:8080`
- You should see the PoolAIssistant dashboard

### 6. Test UI Features

#### A. Home Page
- ✅ Should show pool tabs at top
- ✅ Should display live readings
- ✅ Numbers should update every few seconds

#### B. Charts
- Click on a pool tab
- Charts should show historical data
- Try different time ranges (1h, 6h, 24h, etc.)
- ✅ Graphs should load without errors

#### C. Alarms Page **← THIS IS THE FIX**
- Click "Alarms" link on a pool page
- ✅ Should show "No active alarms" or list of active alarms
- ✅ Should show "Recent changes" section
- ✅ Status dot should be blue (no alarms) or red (active alarms)
- ✅ "Updated: [time] — Active alarms: 0" should appear

**If alarms don't load:**
- Open browser developer tools (F12)
- Check Console tab for errors
- Check Network tab - look for `/alarms/api/Pool%201` request
- Should return JSON with `active` and `recent` arrays

#### D. Maintenance Log
- Navigate to Maintenance section
- Add a test maintenance action
- ✅ Should be logged successfully
- View maintenance logs
- ✅ Your test entry should appear

#### E. Settings
- Navigate to Settings
- ✅ Should show configured controllers
- ✅ System info should be populated
- ✅ Can modify settings

### 7. Test Alarm Detection (Optional)

To test that alarms work properly, you need to trigger an error on your pool controller:

**Method 1: Trigger a real alarm**
- Disconnect a probe temporarily
- Wait for controller to detect fault
- Check PoolAIssistant alarms page - should show active alarm
- Reconnect probe
- Alarm should clear and appear in "Recent changes"

**Method 2: Check database manually**
```sql
sqlite3 pool_readings.sqlite3

-- Insert a test alarm
INSERT INTO alarm_events (started_ts, ended_ts, pool, host, system_name, serial_number, source_label, bit_name)
VALUES (datetime('now'), NULL, 'Pool 1', '10.0.30.80', 'Test System', '12345', 'ErrorCode_pH', 'b0');

-- Check alarms page in browser - should show test alarm

-- Clear the test alarm
UPDATE alarm_events
SET ended_ts = datetime('now')
WHERE ended_ts IS NULL AND source_label = 'ErrorCode_pH';

-- Check alarms page - alarm should move to "Recent changes"

.quit
```

---

## Deployment to Raspberry Pi

Once all tests pass on PC, deploy to the Pi.

### Method 1: Automated Deployment (Recommended)

**On Windows:**
```bash
deploy_to_pi.bat
```

**On Linux/Mac:**
```bash
./deploy_to_pi.sh
```

The script will:
1. Test Pi connectivity
2. Transfer all files
3. Run setup script on Pi
4. Display status

### Method 2: Manual Deployment

```bash
# From your PC, transfer files
scp -r PoolDash_v6 poolassistant@10.0.30.80:/home/poolassistant/

# SSH to Pi
ssh poolassistant@10.0.30.80

# On the Pi
cd PoolDash_v6

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Test connection
python test_modbus_connection.py

# If test passes, install as service
sudo bash setup_pooldash.sh
```

---

## Post-Deployment Testing (On Pi)

### 1. Check Services Are Running

```bash
ssh poolassistant@10.0.30.80

# Check logger service
sudo systemctl status poolaissistant_logger

# Should show: Active: active (running)

# Check UI service
sudo systemctl status poolaissistant_ui

# Should show: Active: active (running)
```

### 2. View Live Logs

```bash
# Logger logs
journalctl -u poolaissistant_logger -f

# UI logs
journalctl -u poolaissistant_ui -f

# Both (press Ctrl+C to exit)
journalctl -u poolaissistant_logger -u poolaissistant_ui -f
```

**What to look for:**
- No error messages
- Regular "wrote N readings" messages every 5 seconds
- No connection timeouts or failures

### 3. Access Web UI Remotely

From your PC:
```
http://10.0.30.80:8080
```

**Test all features again:**
- ✅ Home page loads
- ✅ Charts display data
- ✅ **Alarms page works** (FIXED!)
- ✅ Maintenance logs work
- ✅ Settings page accessible

### 4. Verify Database on Pi

```bash
ssh poolassistant@10.0.30.80

# Check database
sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3

# Run same SQL tests as before
SELECT COUNT(*) FROM readings;
SELECT COUNT(*) FROM alarm_events;
.quit
```

### 5. Performance Check

```bash
ssh poolassistant@10.0.30.80

# Check CPU usage (should be low, <10%)
top -bn1 | grep python

# Check memory usage
free -h

# Check disk usage
df -h
```

---

## Troubleshooting Test Failures

### Logger Won't Start

**Error: "No pools configured"**
- Check `instance/pooldash_settings.json` exists
- Verify controllers are enabled: `"enabled": true`

**Error: "Connection failed"**
- Run `python test_modbus_connection.py`
- Check controller IP and port
- Verify network connectivity

**Error: "Permission denied" on database**
- Check database directory permissions
- On Pi: `sudo chown -R poolassistant:poolassistant /opt/PoolAIssistant/data/`

### Web UI Won't Start

**Error: "Address already in use"**
- Port 8080 is taken
- Stop other service: `sudo systemctl stop poolaissistant_ui`
- Or change port in `run_ui.py`

**Error: "Module not found"**
- Virtual environment not activated
- Run: `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\activate` (Windows)
- Reinstall requirements: `pip install -r requirements.txt`

### Alarms Not Working

**Symptoms:**
- Alarms page blank or shows error
- Browser console shows JavaScript errors
- `/alarms/api/Pool%201` returns error

**Solution:**
- Verify you applied the fix from this review
- Check `pooldash_app/blueprints/alarms.py` doesn't reference `row["meta"]`
- Restart UI service: `sudo systemctl restart poolaissistant_ui`

**Verify fix is applied:**
```bash
# Check alarms.py doesn't have parse_meta function
grep -n "parse_meta" pooldash_app/blueprints/alarms.py
# Should return nothing (or comment lines only)
```

### Database Issues

**Error: "database is locked"**
- WAL mode should prevent this
- If it happens, check for multiple logger instances running
- Kill duplicates: `pkill -f modbus_logger.py`

**No data in database**
- Check logger is running and successfully writing
- Check logs for errors: `journalctl -u poolaissistant_logger`

---

## Test Checklist

Use this checklist before considering deployment complete:

**Pre-Deployment (PC):**
- [ ] Virtual environment created and activated
- [ ] Dependencies installed successfully
- [ ] `test_modbus_connection.py` passes
- [ ] Logger starts and writes to database
- [ ] Database has readings table with data
- [ ] Web UI starts without errors
- [ ] Home page displays pool data
- [ ] Charts load and display data
- [ ] **Alarms page loads without errors** ← CRITICAL FIX
- [ ] Maintenance logs work
- [ ] Settings page accessible

**Deployment:**
- [ ] Files transferred to Pi successfully
- [ ] Services installed and enabled

**Post-Deployment (Pi):**
- [ ] Logger service running
- [ ] UI service running
- [ ] No errors in logs
- [ ] Web UI accessible from PC
- [ ] All features tested and working
- [ ] Database growing (readings being logged)
- [ ] CPU/memory usage acceptable (<10% CPU, <100MB RAM total)

**24-Hour Soak Test:**
- [ ] Leave running for 24 hours
- [ ] Check logs next day for errors
- [ ] Verify continuous data logging
- [ ] Check database size is reasonable
- [ ] Services still running

---

## Success Criteria

Your deployment is successful when:

1. ✅ Services run continuously for 24+ hours without errors
2. ✅ Database steadily accumulates readings every 5 seconds
3. ✅ Web UI remains responsive
4. ✅ **Alarms display correctly when faults occur**
5. ✅ CPU usage stays below 10% average
6. ✅ No memory leaks (memory usage stable)
7. ✅ No connection timeouts or Modbus errors

---

## Automated Testing Script

For advanced users, here's a quick test script:

```bash
#!/bin/bash
# Save as: test_all.sh

echo "Running PoolAIssistant test suite..."

# Test 1: Connection
echo "[1/5] Testing Modbus connection..."
python test_modbus_connection.py || exit 1

# Test 2: Start logger in background
echo "[2/5] Starting logger..."
python modbus_logger.py &
LOGGER_PID=$!
sleep 10

# Test 3: Check database
echo "[3/5] Checking database..."
if [ ! -f "pool_readings.sqlite3" ]; then
    echo "ERROR: Database not created"
    kill $LOGGER_PID
    exit 1
fi

COUNT=$(sqlite3 pool_readings.sqlite3 "SELECT COUNT(*) FROM readings;")
if [ "$COUNT" -lt 1 ]; then
    echo "ERROR: No readings in database"
    kill $LOGGER_PID
    exit 1
fi
echo "OK - $COUNT readings in database"

# Test 4: Start UI and test endpoint
echo "[4/5] Testing web UI..."
python run_ui.py &
UI_PID=$!
sleep 5

curl -s http://localhost:8080/ > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Web UI not responding"
    kill $LOGGER_PID $UI_PID
    exit 1
fi
echo "OK - Web UI responding"

# Test 5: Test alarms endpoint
echo "[5/5] Testing alarms API..."
RESPONSE=$(curl -s http://localhost:8080/alarms/api/Pool%201)
if echo "$RESPONSE" | grep -q "active"; then
    echo "OK - Alarms API working"
else
    echo "ERROR: Alarms API failed"
    kill $LOGGER_PID $UI_PID
    exit 1
fi

# Cleanup
kill $LOGGER_PID $UI_PID
echo
echo "========================================
All Tests Passed!"
echo "========================================

---

## Multi-Site Deployment Testing

### Testing Network-Universal Configuration

After implementing network-universal changes, verify the system works across different network configurations.

#### Test 1: Verify No Hardcoded IPs

```bash
# Search for hardcoded IPs in production code
cd "C:\Users\bensa\iCloudDrive\MBSoftware\PoolAIssitant v6.1.1\PoolDash_v6"
grep -r "192\.168\.\|10\.0\." *.py *.sh *.bat | grep -v ".pyc" | grep -v "example" | grep -v "template"
```

**Expected**: Only example code and comments should contain hardcoded IPs.

#### Test 2: Test Deployment Script with Different Targets

```bash
# Test with environment variable
DEPLOY_TARGET=poolaissitant@192.168.1.100 ./deploy_to_pi.sh

# Test with command-line argument
./deploy_to_pi.sh poolaissitant@10.0.50.80
```

**Expected**: Script accepts target and parses user@host correctly.

#### Test 3: Test Clone Preparation

On a test Pi (or current Pi in test mode):

```bash
ssh poolaissitant@10.0.30.80
sudo bash /opt/PoolAIssistant/app/clone_prep.sh
```

**Expected**:
- Services stop
- Databases backed up and cleared
- Template settings created
- FIRST_BOOT marker created
- Logs cleaned
- SSH host keys removed

#### Test 4: Test First-Boot Setup (Dry Run)

On a cloned system:

```bash
sudo bash /opt/PoolAIssistant/app/first_boot_setup.sh
```

**Expected**:
- Interactive prompts for site name
- Prompts for controller configuration
- IP connectivity tests
- Settings JSON generated
- Services start automatically
- Web UI accessible

#### Test 5: Test Pre-Configuration

On PC with SD card mounted:

```bash
# Create test site config
cat > test_site.json << 'EOFCFG'
{
  "controllers": [
    {
      "enabled": true,
      "host": "192.168.99.10",
      "name": "Test Pool",
      "port": 502,
      "volume_l": 10000
    }
  ],
  "modbus_profile": "ezetrol",
  "ezetrol_layout": "CDAB"
}
EOFCFG

# Mount SD card (replace /dev/sdX2 with actual partition)
sudo mount /dev/sdX2 /mnt/sd_card

# Run pre-configuration
./pre_configure.sh /mnt/sd_card test_site.json

# Verify
cat /mnt/sd_card/opt/PoolAIssistant/data/pooldash_settings.json
ls -l /mnt/sd_card/opt/PoolAIssistant/data/PRE_CONFIGURED

# Unmount
sudo umount /mnt/sd_card
```

**Expected**:
- Settings copied to SD card
- PRE_CONFIGURED marker created
- FIRST_BOOT marker removed

#### Test 6: Different Network Subnet Testing

Test with controllers on different subnets:

**Test Case 1**: Pi and controllers on same subnet
```
Pi: 192.168.1.100
Controllers: 192.168.1.10, 192.168.1.11
```

**Test Case 2**: Pi on different subnet (via routing)
```
Pi: 10.0.30.80
Controllers: 192.168.200.11, 192.168.200.12
```

**Test Case 3**: Pi and controllers on different private subnet
```
Pi: 10.10.50.100
Controllers: 10.10.50.10, 10.10.50.11
```

For each test case:
1. Configure Pi with appropriate settings
2. Test connectivity: `ping <controller-ip>`
3. Test Modbus: `python3 test_modbus_connection.py`
4. Start services and verify data logging
5. Access web UI and verify live data display

#### Test 7: Master Image Creation and Deployment

**On Current Pi**:
```bash
# 1. Run clone prep
ssh poolaissitant@10.0.30.80
sudo bash /opt/PoolAIssistant/app/clone_prep.sh
sudo shutdown -h now

# 2. Create image (on PC)
sudo dd if=/dev/sdX of=test_master.img bs=4M status=progress

# 3. Flash to new card
sudo dd if=test_master.img of=/dev/sdY bs=4M status=progress

# 4. Boot and verify first-boot process
```

**Expected**:
- Image creates successfully
- New Pi boots from cloned card
- First-boot marker detected
- Interactive setup launches
- After setup, services start and data logs

---

## Deployment Validation Checklist

Use this checklist for each new site deployment:

### Pre-Deployment
- [ ] Site survey completed (controller IPs, network details)
- [ ] Site configuration JSON created
- [ ] SD card flashed with master image
- [ ] (If pre-configuring) SD card pre-configured with site settings

### On-Site Deployment
- [ ] Pi connected to power (5V 3A minimum)
- [ ] Pi connected to network (Ethernet preferred)
- [ ] Pi boots successfully (green LED activity)
- [ ] Pi obtains IP address (check router or use nmap)
- [ ] Can SSH to Pi
- [ ] (If not pre-configured) First-boot setup completed
- [ ] All controller IPs entered correctly
- [ ] Controller connectivity tested

### Post-Deployment Verification
- [ ] Services running: `sudo systemctl status poolaissistant_logger poolaissistant_ui`
- [ ] Logger writing data: `journalctl -u poolaissistant_logger -n 20`
- [ ] No errors in logs
- [ ] Web UI accessible at `http://<pi-ip>:8080`
- [ ] All pools showing in UI
- [ ] Live data updating (check timestamps)
- [ ] Charts displaying historical data
- [ ] Alarms page accessible and functional
- [ ] Settings page displays correct controller IPs
- [ ] Maintenance log working

### Long-Term Monitoring (First 24 Hours)
- [ ] Database growing (check file size): `ls -lh /opt/PoolAIssistant/data/pool_readings.sqlite3`
- [ ] No service restarts: `systemctl status poolaissistant_*`
- [ ] No memory issues: `free -h`
- [ ] No disk space issues: `df -h`
- [ ] Logs clean (no repeated errors): `journalctl -u poolaissistant_logger --since "1 hour ago"`

---

## Troubleshooting Common Deployment Issues

### Issue: Cannot SSH to Pi After Cloning

**Cause**: SSH host keys were removed during clone prep

**Solution**: 
1. Connect monitor and keyboard to Pi
2. Log in directly (user: poolaissitant)
3. Regenerate host keys: `sudo dpkg-reconfigure openssh-server`
4. Or wait for first boot to auto-regenerate

### Issue: First-Boot Setup Not Launching

**Cause**: FIRST_BOOT marker missing or removed

**Solution**:
```bash
sudo touch /opt/PoolAIssistant/data/FIRST_BOOT
sudo bash /opt/PoolAIssistant/app/first_boot_setup.sh
```

### Issue: Pre-Configured Pi Not Starting Services

**Cause**: Database initialization failed or settings invalid

**Solution**:
1. Check settings: `cat /opt/PoolAIssistant/data/pooldash_settings.json`
2. Validate JSON: `python3 -m json.tool /opt/PoolAIssistant/data/pooldash_settings.json`
3. Check logs: `journalctl -u poolaissistant_logger -n 50`
4. Initialize DB manually:
   ```bash
   cd /opt/PoolAIssistant/app
   source /opt/PoolAIssistant/venv/bin/activate
   python3 -c "from modbus_logger import init_db; init_db()"
   ```

### Issue: Controllers Not Reachable After Deployment

**Cause**: Network configuration or routing issue

**Solution**:
1. Test connectivity: `ping <controller-ip>`
2. Check routing: `ip route show`
3. Check firewall: `sudo ufw status`
4. Verify controller IPs correct: `cat /opt/PoolAIssistant/data/pooldash_settings.json`
5. Test Modbus: `python3 test_modbus_connection.py --host <controller-ip> --port 502`

---

## Performance Benchmarks

Expected performance on Raspberry Pi 4 (2GB):

| Metric | Value |
|--------|-------|
| Poll interval | 5 seconds (4 controllers) |
| CPU usage (idle) | < 5% |
| CPU usage (polling) | 10-15% |
| Memory usage | ~150MB |
| Database growth | ~10MB/day (4 controllers) |
| Web UI response time | < 500ms |
| Chart load time | < 2s (24h data) |

If performance degrades:
1. Check database size: `ls -lh /opt/PoolAIssistant/data/pool_readings.sqlite3`
2. Vacuum database: `sqlite3 /opt/PoolAIssistant/data/pool_readings.sqlite3 "VACUUM;"`
3. Check for errors: `journalctl -u poolaissistant_logger --since "1 hour ago" | grep -i error`

---

**Testing Guide Version**: 6.1.1 (Universal Deployment)
**Last Updated**: 2026-01-30
**Status**: ✅ Complete
