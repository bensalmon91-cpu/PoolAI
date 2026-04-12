# BAYROL Integration Plan

**Created**: 2026-03-25
**Status**: Ready for implementation
**Priority**: High (FAULT #2 in DISCREPANCY_LOG.md)

---

## Problem

The BAYROL profile crashes the logger with:
```
ValueError: No POINTS defined in modbus.bayrol_modbus_points
```

The BAYROL module uses a different architecture (dictionaries + custom reader class) instead of the `POINTS` list format used by Ezetrol/Dulcopool.

---

## Solution: Integrate BayrolPoolManagerModbus Reader

Modify `modbus_logger.py` to detect BAYROL profile and use the existing `BayrolPoolManagerModbus` class instead of generic POINTS-based reading.

**Why this approach:**
- Reuses existing, tested reader class
- Single service handles all profiles (no duplication)
- Zero risk to Ezetrol/Dulcopool functionality
- Extensible for future protocols

---

## Files to Modify

### Primary: `PoolDash_v6/tools/modbus_logger.py`

Location on Pi: `/opt/PoolAIssistant/app/tools/modbus_logger.py`

### Changes Required:

#### 1. Add BAYROL Detection (~line 53, module level)
```python
IS_BAYROL_PROFILE = False
BAYROL_MODULE = None
```

#### 2. Modify `_load_points()` (~line 283)
```python
def _load_points():
    global IS_BAYROL_PROFILE, BAYROL_MODULE
    # ... existing profile detection ...

    if profile == "bayrol":
        IS_BAYROL_PROFILE = True
        BAYROL_MODULE = module
        return [], {}  # Empty POINTS - use reader instead

    # ... existing code for ezetrol/dulcopool unchanged ...
```

#### 3. Add Label Mapping (~line 580)
```python
BAYROL_LABEL_MAP = {
    # Measurements
    "ph": "pH_MeasuredValue",
    "freecl_br": "Chlorine_MeasuredValue",
    "redox": "ORP_MeasuredValue",
    "t1": "Temp_MeasuredValue",
    "t2": "Temp2_MeasuredValue",
    "t3": "Temp3_MeasuredValue",
    "battery_v": "Battery_Voltage",
    "o2_dosed_amount": "O2_DosedAmount",
    # Parameters
    "setpoint_ph": "pH_Setpoint",
    "setpoint_freecl_br": "Chlorine_Setpoint",
    "setpoint_redox_1": "ORP_Setpoint",
    "low_alarm_ph": "pH_AlarmLow",
    "high_alarm_ph": "pH_AlarmHigh",
    "low_alarm_freecl_br": "Chlorine_AlarmLow",
    "high_alarm_freecl_br": "Chlorine_AlarmHigh",
}

# Tiered alarm polling (30 alarms, but only check critical ones every cycle)
BAYROL_ALARM_CRITICAL = [
    "collective_alarm", "no_flow_input_flow", "no_flow_input_in1",
    "upper_alarm_ph", "lower_alarm_ph", "dosing_alarm_ph",
    "upper_alarm_chlor_br", "lower_alarm_chlor_br", "dosing_alarm_chlor_br",
]

BAYROL_ALARM_IMPORTANT = [
    "upper_alarm_redox", "lower_alarm_redox", "dosing_alarm_redox",
    "upper_alarm_t1", "lower_alarm_t1", "upper_alarm_t2", "lower_alarm_t2",
    "level_alarm_chlor", "level_alarm_redox", "level_alarm_o2",
]

BAYROL_ALARM_WARNING = [
    "power_on_delay", "level_warning_chlor", "level_warning_redox",
    "battery_alarm", "level_alarm_flockmatic",
]
```

#### 4. Add BAYROL Polling Function (~line 1130)
```python
def poll_bayrol_controller(pool_name, host, port, unit, con, health, last_alarm_state, poll_count):
    """Poll a BAYROL controller using BayrolPoolManagerModbus."""
    from modbus.bayrol_modbus_points import BayrolPoolManagerModbus, MEAS_REGS, ALARM_INPUTS

    ts = utc_now_iso()
    system_name = "BAYROL PM5"
    serial_number = ""

    pm = BayrolPoolManagerModbus(host=host, port=port, unit_id=unit, timeout_s=MODBUS_TIMEOUT)
    if not pm.connect():
        health.record_failure(ts, "BAYROL connect failed")
        return 0, last_alarm_state

    try:
        reading_rows = []

        # Read all measurements (every cycle)
        for key in MEAS_REGS.keys():
            try:
                value = pm.read_measurement(key)
                label = BAYROL_LABEL_MAP.get(key, key)
                if value is not None:
                    reading_rows.append((ts, pool_name, host, system_name, serial_number, label, safe_float(value), "f32"))
                    cache_value(host, label, value)
            except Exception as e:
                logging.debug("[%s %s] BAYROL meas %s error: %s", pool_name, host, key, e)

        # Read alarms with tiered frequency
        alarms_to_check = list(BAYROL_ALARM_CRITICAL)
        if poll_count % 3 == 0:
            alarms_to_check.extend(BAYROL_ALARM_IMPORTANT)
        if poll_count % 10 == 0:
            alarms_to_check.extend(BAYROL_ALARM_WARNING)

        new_alarm_state = dict(last_alarm_state)
        for alarm_key in alarms_to_check:
            try:
                is_active = pm.read_alarm(alarm_key)
                prev_state = last_alarm_state.get(alarm_key)
                if prev_state is not None and is_active != prev_state:
                    if is_active:
                        db_open_alarm(con, ts, pool_name, host, system_name, serial_number, "BAYROL_Alarm", alarm_key)
                        logging.info("[%s %s] BAYROL alarm ON: %s", pool_name, host, alarm_key)
                    else:
                        db_close_alarm(con, ts, pool_name, host, "BAYROL_Alarm", alarm_key)
                        logging.info("[%s %s] BAYROL alarm OFF: %s", pool_name, host, alarm_key)
                new_alarm_state[alarm_key] = is_active
            except Exception:
                pass

        if reading_rows:
            db_insert_readings(con, reading_rows)
        db_upsert_meta(con, host, pool_name, system_name, serial_number, ts)
        con.commit()

        health.record_success(ts)
        logging.info("[%s %s] BAYROL wrote %d readings", pool_name, host, len(reading_rows))
        return len(reading_rows), new_alarm_state

    except Exception as e:
        health.record_failure(ts, f"BAYROL error: {e}")
        logging.error("[%s %s] BAYROL error: %s", pool_name, host, e)
        return 0, last_alarm_state
    finally:
        pm.close()
```

#### 5. Add BAYROL Main Loop and Branch in `main()` (~line 1256)
```python
def main():
    # ... existing setup ...

    if IS_BAYROL_PROFILE:
        logging.info("BAYROL profile - using BayrolPoolManagerModbus reader")
        return main_bayrol_loop(con, db_path)

    # ... existing ezetrol/dulcopool code unchanged ...


def main_bayrol_loop(con, db_path):
    """Main polling loop for BAYROL controllers."""
    global _poll_count

    pools = parse_pools()
    if not pools:
        logging.error("No pools configured")
        return 1

    logging.info("BAYROL mode: Polling %d pools every %.1fs", len(pools), SAMPLE_SECONDS)
    notify_ready()

    bayrol_alarm_states = {}  # {host: {alarm_key: bool}}

    while True:
        loop_start = time.time()
        _poll_count += 1

        for pool_name, cfg in pools.items():
            host = cfg["host"]
            port = int(cfg.get("port", 502))
            unit = int(cfg.get("unit", 1))

            health = get_controller_health(host, pool_name)
            if BACKOFF_ENABLED and health.should_skip_this_cycle():
                continue

            if host not in bayrol_alarm_states:
                bayrol_alarm_states[host] = {}

            _, new_state = poll_bayrol_controller(
                pool_name, host, port, unit, con, health,
                bayrol_alarm_states[host], _poll_count
            )
            bayrol_alarm_states[host] = new_state

            db_update_controller_health(con, health)
            con.commit()

        notify_watchdog()
        elapsed = time.time() - loop_start
        time.sleep(max(0.1, SAMPLE_SECONDS - elapsed))

    return 0
```

---

## Testing Procedure

### 1. Update Simulator Config
```json
{
  "units": [{
    "name": "Pool 1 (BAYROL PM5)",
    "port": 502,
    "brand": "BAYROL",
    "model": "PM5",
    "manual_overrides": {
      "enabled": true,
      "measurements": {"ph": 7.35, "freecl_br": 1.20, "redox": 695, "t1": 27.5}
    }
  }]
}
```

### 2. Update Consumer Settings
```json
{
  "modbus_profile": "bayrol",
  "controllers": [{"host": "192.168.1.140", "port": 502, "name": "BAYROL Test"}]
}
```

### 3. Restart and Verify
```bash
sudo systemctl restart poolaissistant_logger
journalctl -u poolaissistant_logger -f
```

### 4. Check Database
```sql
SELECT point_label, value, ts FROM readings WHERE host='192.168.1.140' ORDER BY ts DESC LIMIT 20;
SELECT * FROM alarm_events WHERE source_label='BAYROL_Alarm';
```

### 5. Backward Compatibility
Switch back to `modbus_profile: "ezetrol"` and verify Ezetrol still works.

---

## Estimated Effort

- ~150 lines new code
- ~20 lines modified
- Testing: 30-60 minutes with simulator

---

## To Start Implementation

Tell Claude: "Implement the BAYROL integration from BAYROL_INTEGRATION_PLAN.md"
