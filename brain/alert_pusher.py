"""
PoolAIssistant Alert Pusher
Proactively sends critical alerts to technicians via SMS/WhatsApp.
Can be run as a scheduled task or daemon.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("alert_pusher.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent


class AlertPusher:
    """Monitors alerts and pushes critical ones to technicians."""

    def __init__(self):
        self.alerts_path = SCRIPT_DIR / "analysis" / "latest_alerts.json"
        self.push_log_path = SCRIPT_DIR / "analysis" / "pushed_alerts.json"
        self.load_push_log()

        # Cooldown: don't re-send same alert within this period
        self.cooldown_hours = 4

    def load_push_log(self):
        """Load log of previously pushed alerts."""
        if self.push_log_path.exists():
            with open(self.push_log_path) as f:
                self.push_log = json.load(f)
        else:
            self.push_log = {"pushed": []}

    def save_push_log(self):
        """Save push log."""
        with open(self.push_log_path, 'w') as f:
            json.dump(self.push_log, f, indent=2)

    def get_alert_key(self, alert: dict) -> str:
        """Generate unique key for an alert."""
        return f"{alert.get('pool')}_{alert.get('sensor')}_{alert.get('level')}"

    def was_recently_pushed(self, alert: dict) -> bool:
        """Check if alert was pushed recently (within cooldown)."""
        key = self.get_alert_key(alert)
        cutoff = datetime.now() - timedelta(hours=self.cooldown_hours)

        for pushed in self.push_log.get("pushed", []):
            if pushed.get("key") == key:
                pushed_time = datetime.fromisoformat(pushed.get("timestamp", "2000-01-01"))
                if pushed_time > cutoff:
                    return True
        return False

    def record_push(self, alert: dict):
        """Record that we pushed an alert."""
        self.push_log["pushed"].append({
            "key": self.get_alert_key(alert),
            "timestamp": datetime.now().isoformat(),
            "alert": alert
        })

        # Keep only last 100 entries
        self.push_log["pushed"] = self.push_log["pushed"][-100:]
        self.save_push_log()

    def check_and_push(self):
        """Check for new critical alerts and push them."""
        if not self.alerts_path.exists():
            logger.info("No alerts file found")
            return

        with open(self.alerts_path) as f:
            data = json.load(f)

        alerts = data.get("alerts", [])
        critical_alerts = [a for a in alerts if a.get("level") == "CRITICAL"]

        if not critical_alerts:
            logger.info("No critical alerts")
            return

        # Import SMS interface
        try:
            from technician_sms import SMSInterface
            sms = SMSInterface()
        except ImportError as e:
            logger.error(f"Could not import SMS interface: {e}")
            return

        pushed_count = 0
        for alert in critical_alerts:
            if self.was_recently_pushed(alert):
                logger.info(f"Skipping (recently pushed): {self.get_alert_key(alert)}")
                continue

            logger.info(f"Pushing alert: {self.get_alert_key(alert)}")
            sms.send_alert(alert, channel="both")
            self.record_push(alert)
            pushed_count += 1

        logger.info(f"Pushed {pushed_count} alerts")

    def run_daemon(self, check_interval_minutes=15):
        """Run as continuous daemon, checking periodically."""
        logger.info(f"Starting alert pusher daemon (interval: {check_interval_minutes} min)")

        while True:
            try:
                self.check_and_push()
            except Exception as e:
                logger.error(f"Error in check cycle: {e}")

            time.sleep(check_interval_minutes * 60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Push critical alerts to technicians")
    parser.add_argument('--daemon', action='store_true', help="Run continuously")
    parser.add_argument('--interval', type=int, default=15, help="Check interval in minutes (default: 15)")
    parser.add_argument('--once', action='store_true', help="Check once and exit")
    args = parser.parse_args()

    pusher = AlertPusher()

    if args.daemon:
        pusher.run_daemon(args.interval)
    else:
        pusher.check_and_push()


if __name__ == '__main__':
    main()
