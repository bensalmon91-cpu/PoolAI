"""
PoolAIssistant Alert Checker
Monitors pool readings against established thresholds
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
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
        
    def check_recent_readings(self, hours=1):
        """Check readings from the last N hours."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        alerts = []
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
                    
                # Check latest value
                latest_ts, latest_val = rows[0]
                alert = self.check_value(pool, sensor, latest_val)
                
                if alert:
                    # Count how many recent readings are also out of range
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
        return alerts
        
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
        
        # Check current values
        alerts = self.check_recent_readings()
        
        if alerts:
            logger.warning(f"Found {len(alerts)} active alerts:")
            for a in alerts:
                logger.warning(f"  [{a['level']}] {a['pool']} {a['sensor']}: {a['current_value']} (normal: {a['normal_range']})")
        else:
            logger.info("No active alerts - all readings within normal range")
            
        # Check trends
        trends = self.check_trends()
        
        if trends:
            logger.info(f"Trend alerts ({len(trends)}):")
            for t in trends:
                logger.info(f"  {t['pool']} {t['sensor']}: {t['direction']} for {t['days']} days (change: {t['total_change']:+.3f})")
        
        # Save results
        results = {
            "check_time": datetime.now().isoformat(),
            "alerts": alerts,
            "trends": trends,
            "status": "CRITICAL" if any(a["level"] == "CRITICAL" for a in alerts) 
                       else "WARNING" if alerts else "OK"
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
