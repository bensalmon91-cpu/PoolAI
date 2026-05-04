"""
PoolAIssistant Alert Checker
Monitors pool readings against established thresholds
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("alerts.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# B4: physically-plausible bands for each sensor type. A reading outside
# these is almost certainly a probe failure, calibration drift, or wiring
# issue — NOT a chemistry event. Real-world commercial pools never see
# pH < 5 (water would etch concrete), Temp < 0 / > 60 (frozen / boiling),
# or ORP < 0 / > 1500 (sensor saturation).
IMPLAUSIBLE_BANDS = {
    "pH":   {"min": 5.0,  "max": 9.0,    "unit": ""},
    "Temp": {"min": 0.0,  "max": 60.0,   "unit": "°C"},
    "ORP":  {"min": 0.0,  "max": 1500.0, "unit": "mV"},
}

# B4: stuck-sensor detection — if all recent readings are within this
# spread AND the value is outside its normal range, the probe is probably
# stuck at a bad value. Tuned slightly above each sensor's normal noise
# floor so quiescent-but-healthy periods don't trip false positives.
STUCK_SPREAD = {
    "pH":   0.05,   # real pH wiggles ≥ 0.05 within an hour from probe noise alone
    "Temp": 0.1,    # water temp moves with circulation
    "ORP":  5.0,    # ORP background noise is normally ±10-20 mV
}
STUCK_MIN_READINGS = 30  # need at least this many to trust the spread

class AlertChecker:
    def __init__(self, db_path="output/pool_readings.db", config_path="config/alert_thresholds.json"):
        # Resolve paths relative to this script's directory
        script_dir = Path(__file__).parent
        self.db_path = script_dir / db_path
        self.config_path = script_dir / config_path
        self.load_config()
        
    def load_config(self):
        with open(self.config_path) as f:
            self.config = json.load(f)
        self.thresholds = self.config["pools"]
        self.sustained_minutes = self.config.get("sustained_duration_minutes", 30)
        
    def check_value(self, pool, sensor, value):
        """Check a single value against thresholds."""
        if pool not in self.thresholds or sensor not in self.thresholds[pool]:
            return None

        t = self.thresholds[pool][sensor]

        if value < t["critical_min"] or value > t["critical_max"]:
            return {"level": "CRITICAL", "value": value, "baseline": t["baseline"],
                    "range": f"{t['critical_min']}-{t['critical_max']}"}
        elif value < t["min"] or value > t["max"]:
            return {"level": "WARNING", "value": value, "baseline": t["baseline"],
                    "range": f"{t['min']}-{t['max']}"}
        return None

    def classify_sensor_fault(self, pool, sensor, recent_readings):
        """Detect probe failures separately from chemistry alerts.

        recent_readings: list of (ts, value), latest first. Returns a fault
        dict (with fault_type ∈ {'implausible_value', 'stuck_at_unusual'})
        or None if the sensor looks healthy.
        """
        if not recent_readings:
            return None
        latest_ts, latest_val = recent_readings[0]

        # 1) Implausibility band — physical limits. Most decisive signal.
        band = IMPLAUSIBLE_BANDS.get(sensor)
        if band and (latest_val < band["min"] or latest_val > band["max"]):
            unit = (" " + band["unit"]) if band["unit"] else ""
            return {
                "pool": pool,
                "sensor": sensor,
                "timestamp": latest_ts,
                "fault_type": "implausible_value",
                "current_value": round(latest_val, 2),
                "plausible_range": f"{band['min']}-{band['max']}{unit}",
                "reason": (
                    f"{pool} {sensor} reading {latest_val:.2f}{unit} is outside the "
                    f"physically plausible range {band['min']}-{band['max']}{unit}. "
                    f"Probable probe failure (dead cell, broken wire, or extreme "
                    f"calibration drift). Investigate the sensor before treating "
                    f"this as a chemistry event."
                ),
            }

        # 2) Stuck-at-unusual — flat readings while outside normal range.
        # If reading is normal, "flat" is fine (just quiescent water).
        threshold_alert = self.check_value(pool, sensor, latest_val)
        if threshold_alert is None:
            return None
        spread_threshold = STUCK_SPREAD.get(sensor)
        if spread_threshold is None or len(recent_readings) < STUCK_MIN_READINGS:
            return None
        values = [v for _, v in recent_readings]
        spread = max(values) - min(values)
        if spread <= spread_threshold:
            return {
                "pool": pool,
                "sensor": sensor,
                "timestamp": latest_ts,
                "fault_type": "stuck_at_unusual",
                "current_value": round(latest_val, 2),
                "plausible_range": f"normal: {threshold_alert['range']}",
                "reason": (
                    f"{pool} {sensor} reading {latest_val:.2f} is flat over the "
                    f"last {len(values)} readings (spread {spread:.3f} ≤ "
                    f"threshold {spread_threshold}) and outside the normal range "
                    f"{threshold_alert['range']}. Probable stuck/dead probe."
                ),
            }
        return None
        
    def check_recent_readings(self, hours=1):
        """Check readings from the last N hours.

        Returns a tuple (alerts, sensor_faults). Sensor faults are
        emitted INSTEAD of chemistry alerts for the same probe — a value
        that's both implausible AND outside threshold is filed only as a
        sensor fault, since the threshold check on a faulty reading is
        meaningless.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        alerts = []
        sensor_faults = []
        sensor_map = {
            "pH_MeasuredValue": "pH",
            "Temp_MeasuredValue": "Temp",
            "ORP_MeasuredValue": "ORP"
        }

        for pool in self.thresholds.keys():
            for db_sensor, sensor in sensor_map.items():
                cursor.execute("""
                    SELECT ts, value FROM readings
                    WHERE pool = ? AND point_label = ?
                    ORDER BY ts DESC LIMIT 100
                """, (pool, db_sensor))

                rows = cursor.fetchall()
                if not rows:
                    continue

                latest_ts, latest_val = rows[0]

                # Sensor fault check first — supersedes chemistry alert when triggered
                fault = self.classify_sensor_fault(pool, sensor, rows)
                if fault is not None:
                    sensor_faults.append(fault)
                    continue

                # Else: standard chemistry-threshold check
                alert = self.check_value(pool, sensor, latest_val)
                if alert:
                    out_of_range = sum(1 for ts, val in rows
                                      if self.check_value(pool, sensor, val))
                    alerts.append({
                        "pool": pool,
                        "sensor": sensor,
                        "timestamp": latest_ts,
                        "level": alert["level"],
                        "current_value": round(alert["value"], 2),
                        "baseline": alert["baseline"],
                        "normal_range": alert["range"],
                        "sustained_readings": out_of_range
                    })

        conn.close()
        return alerts, sensor_faults
        
    def check_staleness(self):
        """Return staleness info dict (always populated) — pipeline-level alert.

        is_stale=True means the newest reading in the DB is older than
        STALENESS_HOURS env var (default 6). This is a meta-alert about the
        pipeline itself, separate from per-sensor alerts.
        """
        threshold_h = float(os.getenv("STALENESS_HOURS", "6"))
        info = {
            "is_stale": False,
            "latest_reading": None,
            "age_hours": None,
            "threshold_hours": threshold_h,
        }
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT MAX(ts) FROM readings").fetchone()
            conn.close()
        except Exception as e:
            logger.warning(f"staleness query failed: {e}")
            return info
        latest = row[0] if row else None
        if not latest:
            return info
        try:
            latest_dt = datetime.fromisoformat(latest)
        except ValueError:
            return info
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 3600.0
        info["latest_reading"] = latest
        info["age_hours"] = round(age_h, 2)
        info["is_stale"] = age_h > threshold_h
        return info

    def check_trends(self):
        """Check for concerning trends (like Spa pH declining)."""
        conn = sqlite3.connect(self.db_path)
        trends = []
        
        for pool in self.thresholds.keys():
            for sensor in ["pH", "Temp", "ORP"]:
                db_sensor = f"{sensor}_MeasuredValue"
                
                # Get daily averages
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DATE(ts) as day, AVG(value) as avg_val
                    FROM readings
                    WHERE pool = ? AND point_label = ?
                    GROUP BY DATE(ts)
                    ORDER BY day
                """, (pool, db_sensor))
                
                daily = cursor.fetchall()
                if len(daily) < 3:
                    continue
                    
                # Check for consistent trend
                diffs = [daily[i+1][1] - daily[i][1] for i in range(len(daily)-1)]
                
                # All increasing or all decreasing
                if all(d > 0 for d in diffs[-3:]):
                    trends.append({
                        "pool": pool, "sensor": sensor,
                        "direction": "RISING",
                        "days": len([d for d in diffs if d > 0]),
                        "total_change": round(sum(diffs[-3:]), 3)
                    })
                elif all(d < 0 for d in diffs[-3:]):
                    trends.append({
                        "pool": pool, "sensor": sensor,
                        "direction": "FALLING",
                        "days": len([d for d in diffs if d < 0]),
                        "total_change": round(sum(diffs[-3:]), 3)
                    })
        
        conn.close()
        return trends
        
    def run_check(self):
        """Run full alert check and return results."""
        logger.info("=" * 50)
        logger.info("PoolAIssistant Alert Check")
        logger.info("=" * 50)
        
        # Pipeline staleness check (B1) — meta-alert, surfaced before per-sensor alerts
        staleness = self.check_staleness()
        if staleness["is_stale"]:
            age_h = staleness["age_hours"]
            logger.warning(
                f"[CRITICAL] Pipeline STALE: newest reading is {age_h:.1f}h old "
                f"(threshold {staleness['threshold_hours']}h). "
                f"Per-sensor alerts below reflect data from {staleness['latest_reading']}, NOT live state."
            )
        elif staleness["age_hours"] is not None:
            logger.info(f"Pipeline freshness OK ({staleness['age_hours']:.1f}h old).")

        # Check current values + sensor faults (faults supersede alerts on the same probe)
        alerts, sensor_faults = self.check_recent_readings()

        if sensor_faults:
            logger.warning(f"Found {len(sensor_faults)} sensor fault(s):")
            for f in sensor_faults:
                logger.warning(
                    f"  [SENSOR_FAULT/{f['fault_type']}] {f['pool']} {f['sensor']}: "
                    f"{f['current_value']} -- {f['reason']}"
                )

        if alerts:
            logger.warning(f"Found {len(alerts)} chemistry alert(s):")
            for a in alerts:
                logger.warning(f"  [{a['level']}] {a['pool']} {a['sensor']}: {a['current_value']} (normal: {a['normal_range']})")
        elif not sensor_faults:
            logger.info("No active alerts - all readings within normal range")

        # Check trends
        trends = self.check_trends()

        if trends:
            logger.info(f"Trend alerts ({len(trends)}):")
            for t in trends:
                logger.info(f"  {t['pool']} {t['sensor']}: {t['direction']} for {t['days']} days (change: {t['total_change']:+.3f})")

        # Status logic:
        #   - sensor faults force CRITICAL (chemistry status is unknown for those probes)
        #   - staleness forces CRITICAL (data is too old to trust)
        #   - else use the worst chemistry alert level
        sensor_alert_status = (
            "CRITICAL" if any(a["level"] == "CRITICAL" for a in alerts)
            else "WARNING" if alerts else "OK"
        )
        overall_status = (
            "CRITICAL"
            if (staleness["is_stale"] or sensor_faults or sensor_alert_status == "CRITICAL")
            else sensor_alert_status
        )

        results = {
            "check_time": datetime.now().isoformat(),
            "staleness": staleness,
            "sensor_faults": sensor_faults,
            "alerts": alerts,
            "trends": trends,
            "status": overall_status,
        }
        
        Path("analysis").mkdir(exist_ok=True)
        with open("analysis/latest_alerts.json", "w") as f:
            json.dump(results, f, indent=2)
            
        logger.info(f"Overall status: {results['status']}")
        logger.info("Results saved to analysis/latest_alerts.json")
        
        return results

if __name__ == "__main__":
    checker = AlertChecker()
    checker.run_check()
