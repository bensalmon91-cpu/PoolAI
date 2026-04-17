"""
PoolAIssistant Brain - Daily Analysis Runner
Run this script to sync data, update baselines, and check for issues.

Usage:
    python run_analysis.py              # Full run: sync + analyze + report
    python run_analysis.py --no-sync    # Skip Azure sync, just analyze local data
    python run_analysis.py --report     # Just show current status report
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from baseline_manager import BaselineManager


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def sync_data():
    """Sync data from Azure."""
    print_header("SYNCING DATA FROM AZURE")
    try:
        from db_sync import main as sync_main
        sync_main()
        return True
    except Exception as e:
        print(f"Sync failed: {e}")
        print("Continuing with local data...")
        return False


def update_baselines(device: str = "Swanwood_Spa", days: int = 30):
    """Update baselines from current data."""
    print_header("UPDATING BASELINES")
    manager = BaselineManager()
    manager.update_all_baselines(device, days)
    return manager


def check_all_deviations(manager: BaselineManager, device: str = "Swanwood_Spa"):
    """Check all pools for deviations."""
    print_header("CHECKING FOR DEVIATIONS")

    all_alerts = []
    pools = manager.baselines.get('pools', {}).keys()

    for pool in pools:
        alerts = manager.check_deviations(device, pool)
        all_alerts.extend(alerts)
        if alerts:
            print(f"\n{pool}: {len(alerts)} alert(s)")
            for alert in alerts:
                icon = "!!" if alert.alert_type == 'alarm' else "!"
                print(f"  {icon} {alert.sensor}: {alert.message}")
        else:
            print(f"\n{pool}: OK")

    return all_alerts


def generate_status_report(manager: BaselineManager):
    """Generate a full status report."""
    print_header("POOL STATUS REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    pools = manager.baselines.get('pools', {})

    for pool_name, pool_data in pools.items():
        print(f"\n{'-' * 50}")
        print(f"  {pool_name.upper()}")
        print(f"{'-' * 50}")

        # Operating ranges
        ranges = pool_data.get('normal_operating_ranges', {})
        if ranges:
            print("\n  Current Readings vs Baseline:")
            for sensor, data in ranges.items():
                short_name = sensor.replace('_MeasuredValue', '')
                mean = data.get('mean', 0)
                p5 = data.get('p5', 0)
                p95 = data.get('p95', 0)
                print(f"    {short_name:12}: {mean:7.2f}  (normal: {p5:.2f} - {p95:.2f})")

        # Pump effectiveness
        pumps = pool_data.get('pump_effectiveness', {})
        if pumps:
            print("\n  Pump Status:")
            for pump_name, pump_data in pumps.items():
                activity = pump_data.get('activity', {})
                pct_active = activity.get('pct_time_active', 0)
                effectiveness = pump_data.get('effectiveness', {})
                red_flag = pump_data.get('red_flag')

                status = "OK"
                if red_flag:
                    status = f"RED FLAG: {red_flag.get('issue', 'ISSUE')}"
                elif isinstance(effectiveness, dict) and effectiveness.get('status') == 'NOT_ACTIVE':
                    status = "NOT ACTIVE"

                print(f"    {pump_name:12}: {pct_active:5.1f}% active  [{status}]")

        # Red flags and issues
        issues = pool_data.get('issues', [])
        if issues:
            print("\n  Known Issues:")
            for issue in issues:
                print(f"    - {issue}")

    print(f"\n{'=' * 50}")


def save_report(manager: BaselineManager, alerts: list, output_dir: Path):
    """Save report to file."""
    report_file = output_dir / 'reports' / f"status_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with open(report_file, 'w') as f:
        f.write(f"PoolAIssistant Status Report\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("=" * 50 + "\n\n")

        for pool_name in manager.baselines.get('pools', {}).keys():
            f.write(manager.get_baseline_summary(pool_name))
            f.write("\n\n")

        if alerts:
            f.write("\nALERTS:\n")
            for alert in alerts:
                f.write(f"- [{alert.alert_type.upper()}] {alert.pool}/{alert.sensor}: {alert.message}\n")

    print(f"\nReport saved: {report_file}")


def main():
    parser = argparse.ArgumentParser(description='PoolAIssistant Daily Analysis')
    parser.add_argument('--no-sync', action='store_true', help='Skip Azure data sync')
    parser.add_argument('--report', action='store_true', help='Just show status report')
    parser.add_argument('--device', default='Swanwood_Spa', help='Device name')
    parser.add_argument('--days', type=int, default=30, help='Days of data for baseline')
    args = parser.parse_args()

    output_dir = Path(os.getenv('OUTPUT_DIR', './output'))

    print("\n" + "=" * 60)
    print("       PoolAIssistant Brain - Analysis Runner")
    print("=" * 60)

    # Report only mode
    if args.report:
        manager = BaselineManager()
        generate_status_report(manager)
        return

    # Full analysis run
    if not args.no_sync:
        sync_data()

    manager = update_baselines(args.device, args.days)
    alerts = check_all_deviations(manager, args.device)
    generate_status_report(manager)
    save_report(manager, alerts, output_dir)

    # Summary
    print_header("SUMMARY")
    alarm_count = sum(1 for a in alerts if a.alert_type == 'alarm')
    warning_count = sum(1 for a in alerts if a.alert_type == 'warning')

    if alarm_count > 0:
        print(f"  !! {alarm_count} ALARM(S) - Immediate attention required")
    if warning_count > 0:
        print(f"  !  {warning_count} WARNING(S) - Review recommended")
    if alarm_count == 0 and warning_count == 0:
        print("  All pools operating within normal parameters")

    print("\n  Next steps:")
    print("  - Review any red flags in pump effectiveness")
    print("  - Check knowledge/investigation_context.md for known issues")
    print("  - Run 'python run_analysis.py --report' for quick status")
    print()


if __name__ == '__main__':
    main()
