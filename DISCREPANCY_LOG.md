# PoolAI vs Simulator Discrepancy Log

**Generated**: 2026-03-25
**Baseline**: Ezetrol Touch protocol (simulator is reference)
**Consumer**: poolai@192.168.1.81
**Simulator**: mbs@192.168.1.140

---

## FAULT #1: Incorrect Validation Logic (Consumer Bug)

**Severity**: Medium
**Location**: `/opt/PoolAIssistant/app/tools/modbus_logger.py:424-445`

### Description
The consumer uses substring matching for validation ranges, which incorrectly applies measurement ranges to control parameters.

### Code (Consumer):
```python
VALID_RANGES = {
    "pH": (0.0, 14.0),
    "Chlorine": (0.0, 20.0),
    ...
}
for key, (vmin, vmax) in VALID_RANGES.items():
    if key in label:  # <-- BUG: substring match is too broad
```

### Affected Parameters:
| Parameter | Actual Value | Validated As | Range Applied | Correct Range |
|-----------|-------------|--------------|---------------|---------------|
| Ctrl1_Chlorine_Xp | 50.0 | "Chlorine" | [0.0, 20.0] | [0.0, 999.0] |
| Ctrl1_Chlorine_Tn | 300.0 | "Chlorine" | [0.0, 20.0] | [0.0, 9999.0] |
| Ctrl2_pH_Xp | 50.0 | "pH" | [0.0, 14.0] | [0.0, 999.0] |
| Ctrl2_pH_Tn | 300.0 | "pH" | [0.0, 14.0] | [0.0, 9999.0] |

### Fix Required
Validation should only apply to `*_MeasuredValue` labels, not control parameters.

### Fix Applied
```python
# Added early return for non-measurement labels:
if not label.endswith("_MeasuredValue"):
    return True
```
**Status**: FIXED on consumer Pi (2026-03-25)

### Evidence
```
Mar 25 06:05:17 PoolAI python[31659]: WARNING [VALIDATION] Ctrl1_Chlorine_Xp=50.0 out of range [0.0, 20.0]
Mar 25 06:05:17 PoolAI python[31659]: WARNING [VALIDATION] Ctrl1_Chlorine_Tn=300.0 out of range [0.0, 20.0]
Mar 25 06:05:17 PoolAI python[31659]: WARNING [VALIDATION] Ctrl2_pH_Xp=50.0 out of range [0.0, 14.0]
Mar 25 06:05:17 PoolAI python[31659]: WARNING [VALIDATION] Ctrl2_pH_Tn=300.0 out of range [0.0, 14.0]
```

---

## FAULT #2: BAYROL Profile Not Integrated with Logger

**Severity**: High
**Location**: `/opt/PoolAIssistant/app/modbus/bayrol_modbus_points.py`
**Tested**: 2026-03-25 18:28 UTC

### Description
The BAYROL module uses a completely different architecture than Ezetrol:
- Uses `PARAM_REGS`, `MEAS_REGS`, `ALARM_INPUTS` dictionaries instead of `POINTS` list
- Has its own `BayrolPoolManagerModbus` reader class
- The generic `modbus_logger.py` expects a `POINTS` list and fails with BAYROL profile

### Error (Confirmed)
```
FATAL: Cannot load Modbus points for profile 'bayrol': No POINTS defined in modbus.bayrol_modbus_points
Traceback (most recent call last):
  File "/opt/PoolAIssistant/app/tools/modbus_logger.py", line 392, in <module>
    POINTS, LABEL_ALIASES = _load_points()
  File "/opt/PoolAIssistant/app/tools/modbus_logger.py", line 309, in _load_points
    raise ValueError(f"No POINTS defined in {module_name}")
ValueError: No POINTS defined in modbus.bayrol_modbus_points
```

### Live Test Results (2026-03-25)
| Effect | Observation |
|--------|-------------|
| Service crash loop | 13+ restart attempts in 5 minutes |
| Data collection | STOPPED - no new readings after profile switch |
| Web UI | Unaffected - running normally |
| Database | Intact - 48,384 historical readings preserved |
| CPU usage | Elevated due to continuous restarts |

### Root Cause Analysis
| Component | Ezetrol | BAYROL |
|-----------|---------|--------|
| Data structure | `POINTS = [...]` list | `PARAM_REGS`, `MEAS_REGS`, `ALARM_INPUTS` dicts |
| Object type | Plain dictionaries | `RegisterDef` dataclass instances |
| Function code | FC03 (holding registers) | FC04 (input regs) + FC02 (discrete inputs) |
| Register addresses | 400001-401108 | 3001-4077 |
| Multi-read | Supported | NOT supported (count=1 only) |

### Fix Required
Either:
1. Add a `POINTS` list adapter to `bayrol_modbus_points.py` + FC04/FC02 handling in logger
2. Or extend `modbus_logger.py` to use `BayrolPoolManagerModbus` reader class
3. Or create separate `bayrol_logger.py` service

### Impact
- Cannot test BAYROL protocol via the standard logger
- Mixed Ezetrol + BAYROL deployments not possible
- BAYROL-only deployments broken
- Settings UI allows selection of non-functional profile

---

## VERIFIED WORKING

### Measurements (Correct)
| Point | Simulator Value | Consumer Read | Status |
|-------|----------------|---------------|--------|
| Chlorine_MeasuredValue | 0.30 → 1.50 | 0.30 → 1.50 | ✓ OK |
| pH_MeasuredValue | 7.40 → 7.20 | 7.40 → 7.20 | ✓ OK |
| ORP_MeasuredValue | 485.00 → 720.00 | 485.00 → 720.00 | ✓ OK |
| Temp_MeasuredValue | 16.20 → 28.50 | 16.20 → 28.50 | ✓ OK |

### Live Value Update Test (PASSED)
Simulator config changed, consumer picked up new values within 5-second polling interval.

### Communication
- Modbus TCP connection: ✓ OK
- FC03 (Holding Registers): ✓ OK
- Float32 decoding (BA word order): ✓ OK
- 5-second polling: ✓ OK
- Database writes: ✓ OK (56 readings initial, 5 per poll cycle)
- Live config changes: ✓ OK (auto-detected within poll interval)

---

## TESTS COMPLETED

### Alarm Register Testing (PASSED)
- Set `status_ctrl1_mode=2` → Consumer detected `Status_Mode_Controller1_Chlorine:b1`
- Set `error_chlorine=1` → Consumer detected `ErrorCode_Chlorine:b0`
- Alarm events correctly stored in `alarm_events` table
- Start timestamp recorded, end timestamp NULL (alarm still active)

### Connection Recovery (PASSED)
- Consumer reconnected after simulator restart within 2 poll cycles
- Recovery logged: "wrote 8 readings [recovered, 85% recent success rate]"

---

### Alarm Clearing (PASSED)
- When `status_ctrl1_mode` and `error_chlorine` set back to 0
- Consumer correctly populated `ended_ts` on both alarm events
- Alarm duration tracked: started 06:14:12, ended 06:16:02

---

## TESTS PENDING

- [ ] Setpoint write operations
- [ ] Multi-controller simulation
- [ ] Network error simulation (packet loss, timeout)
- [ ] Compare with real Ezetrol hardware
- [x] BAYROL PM5 protocol testing → **BLOCKED** by FAULT #2 (integration required)
- [ ] Dulcopool Pro protocol testing

---
