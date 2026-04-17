"""
PoolAIssistant Brain - Baseline Manager
Establishes, updates, and compares against pool operating baselines.
Detects deviations from normal behavior.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('baseline_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DeviationAlert:
    """Represents a detected deviation from baseline."""
    pool: str
    sensor: str
    alert_type: str  # 'warning' or 'alarm'
    category: str    # 'value', 'correlation', 'response_time', 'slope'
    message: str
    current_value: float
    baseline_value: float
    deviation_amount: float
    timestamp: str


class BaselineManager:
    """Manages pool baselines and deviation detection."""

    def __init__(self):
        load_dotenv()
        self.chunks_dir = Path(os.getenv('LOCAL_CHUNKS_DIR', './data/chunks'))
        self.output_dir = Path(os.getenv('OUTPUT_DIR', './output'))
        # Knowledge files stored at root level for git tracking
        self.knowledge_dir = Path('./knowledge')
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        self.baselines_file = self.knowledge_dir / 'pool_baselines.json'
        self.deviations_file = self.knowledge_dir / 'detected_deviations.json'

        self.baselines = self._load_baselines()

    def _load_baselines(self) -> dict:
        """Load existing baselines."""
        if self.baselines_file.exists():
            with open(self.baselines_file, 'r') as f:
                return json.load(f)
        return {"_metadata": {"version": "1.0"}, "pools": {}}

    def _save_baselines(self):
        """Save baselines to file."""
        self.baselines['_metadata']['last_updated'] = datetime.now().isoformat()
        with open(self.baselines_file, 'w') as f:
            json.dump(self.baselines, f, indent=2, default=str)
        logger.info(f"Baselines saved: {self.baselines_file}")

    def _load_pool_data(self, device_name: str, pool_name: str,
                        days_back: int = 14) -> pd.DataFrame:
        """Load recent data for a pool."""
        device_dir = self.chunks_dir / device_name
        if not device_dir.exists():
            return pd.DataFrame()

        all_dfs = []
        cutoff = datetime.now() - timedelta(days=days_back)

        for db_file in device_dir.glob("*.db"):
            try:
                conn = sqlite3.connect(str(db_file))
                df = pd.read_sql_query(
                    f"SELECT * FROM readings WHERE pool = '{pool_name}'",
                    conn
                )
                conn.close()
                df['ts'] = pd.to_datetime(df['ts'], utc=True)
                # Make cutoff timezone-aware for comparison
                cutoff_aware = pd.Timestamp(cutoff, tz='UTC')
                # Filter to recent data
                df = df[df['ts'] >= cutoff_aware]
                if not df.empty:
                    all_dfs.append(df)
            except Exception as e:
                logger.debug(f"Error loading {db_file}: {e}")

        if not all_dfs:
            return pd.DataFrame()

        combined = pd.concat(all_dfs, ignore_index=True)
        return combined.sort_values('ts').drop_duplicates()

    def calculate_baseline(self, device_name: str, pool_name: str,
                          days_back: int = 14) -> dict:
        """Calculate baseline statistics for a pool."""
        logger.info(f"Calculating baseline for {device_name}/{pool_name}")

        df = self._load_pool_data(device_name, pool_name, days_back)
        if df.empty:
            logger.warning(f"No data for {pool_name}")
            return None

        # Pivot to time series
        pivoted = df.pivot_table(
            index='ts', columns='point_label', values='value', aggfunc='mean'
        )
        pivoted = pivoted.resample('1min').mean()

        baseline = {
            'last_baseline_update': datetime.now().isoformat(),
            'data_period': {
                'start': str(pivoted.index.min()),
                'end': str(pivoted.index.max())
            },
            'data_points_in_baseline': len(pivoted),
            'normal_operating_ranges': {},
            'established_correlations': {}
        }

        # Calculate statistics for key sensors
        key_sensors = [
            'Chlorine_MeasuredValue', 'pH_MeasuredValue',
            'ORP_MeasuredValue', 'Temp_MeasuredValue'
        ]

        for sensor in key_sensors:
            if sensor not in pivoted.columns:
                continue

            series = pivoted[sensor].dropna()
            if len(series) < 100:
                continue

            baseline['normal_operating_ranges'][sensor] = {
                'count': len(series),
                'mean': round(float(series.mean()), 4),
                'std': round(float(series.std()), 4),
                'min': round(float(series.min()), 4),
                'max': round(float(series.max()), 4),
                'p5': round(float(series.quantile(0.05)), 4),
                'p25': round(float(series.quantile(0.25)), 4),
                'p50': round(float(series.quantile(0.50)), 4),
                'p75': round(float(series.quantile(0.75)), 4),
                'p95': round(float(series.quantile(0.95)), 4)
            }

        # Calculate correlations
        if 'Chlorine_MeasuredValue' in pivoted.columns and 'ORP_MeasuredValue' in pivoted.columns:
            cl = pivoted['Chlorine_MeasuredValue'].dropna()
            orp = pivoted['ORP_MeasuredValue'].dropna()
            common = cl.index.intersection(orp.index)

            if len(common) > 100:
                cl_aligned = cl[common]
                orp_aligned = orp[common]

                corr = cl_aligned.corr(orp_aligned)
                slope, intercept, r, p, se = stats.linregress(cl_aligned, orp_aligned)

                # Find best lag
                best_lag = 0
                best_corr = corr
                for lag in range(1, 31):
                    shifted = orp_aligned.shift(-lag)
                    c = cl_aligned.corr(shifted.dropna())
                    if not np.isnan(c) and abs(c) > abs(best_corr):
                        best_corr = c
                        best_lag = lag

                baseline['established_correlations']['chlorine_orp'] = {
                    'correlation': round(float(corr), 4),
                    'slope': round(float(slope), 2),
                    'intercept': round(float(intercept), 2),
                    'r_squared': round(float(r**2), 4),
                    'best_lag_minutes': best_lag,
                    'best_correlation': round(float(best_corr), 4)
                }

        if 'pH_MeasuredValue' in pivoted.columns and 'ORP_MeasuredValue' in pivoted.columns:
            ph = pivoted['pH_MeasuredValue'].dropna()
            orp = pivoted['ORP_MeasuredValue'].dropna()
            common = ph.index.intersection(orp.index)

            if len(common) > 100:
                ph_aligned = ph[common]
                orp_aligned = orp[common]

                corr = ph_aligned.corr(orp_aligned)
                slope, intercept, r, p, se = stats.linregress(ph_aligned, orp_aligned)

                baseline['established_correlations']['orp_ph'] = {
                    'correlation': round(float(corr), 4),
                    'slope': round(float(slope), 2),
                    'intercept': round(float(intercept), 2),
                    'r_squared': round(float(r**2), 4)
                }

        if 'Chlorine_MeasuredValue' in pivoted.columns and 'pH_MeasuredValue' in pivoted.columns:
            cl = pivoted['Chlorine_MeasuredValue'].dropna()
            ph = pivoted['pH_MeasuredValue'].dropna()
            common = cl.index.intersection(ph.index)

            if len(common) > 100:
                baseline['established_correlations']['chlorine_ph'] = {
                    'correlation': round(float(cl[common].corr(ph[common])), 4)
                }

        # Calculate pump effectiveness metrics
        baseline['pump_effectiveness'] = self._calculate_pump_effectiveness(pivoted)

        return baseline

    def _calculate_pump_effectiveness(self, pivoted: pd.DataFrame) -> dict:
        """
        Calculate pump output vs result metrics.

        Key metrics:
        - Activity profile: how often pump runs, average output
        - Effectiveness: measured change per unit of pump output
        - Red flags: high output with no result
        """
        pump_metrics = {}

        # Define pump-to-sensor mappings
        pump_mappings = [
            {
                'pump': 'Chlorine_Yout',
                'sensor': 'Chlorine_MeasuredValue',
                'name': 'chlorine',
                'unit': 'mg/L per %-min'
            },
            {
                'pump': 'pH_Yout',
                'sensor': 'pH_MeasuredValue',
                'name': 'ph',
                'unit': 'pH per %-min',
                'invert': True  # pH dosing typically lowers pH
            }
        ]

        for mapping in pump_mappings:
            pump_col = mapping['pump']
            sensor_col = mapping['sensor']
            name = mapping['name']

            if pump_col not in pivoted.columns or sensor_col not in pivoted.columns:
                continue

            pump = pivoted[pump_col].dropna()
            sensor = pivoted[sensor_col].dropna()
            common = pump.index.intersection(sensor.index)

            if len(common) < 100:
                continue

            pump = pump[common]
            sensor = sensor[common]

            # Activity profile
            active_threshold = 1.0  # Consider pump "active" if Yout > 1%
            active_mask = pump > active_threshold
            pct_time_active = round(float(active_mask.mean() * 100), 2)
            mean_output_when_active = round(float(pump[active_mask].mean()), 2) if active_mask.any() else 0

            metrics = {
                'activity': {
                    'mean_output_pct': round(float(pump.mean()), 2),
                    'max_output_pct': round(float(pump.max()), 2),
                    'pct_time_active': pct_time_active,
                    'mean_when_active': mean_output_when_active
                }
            }

            # Calculate effectiveness: look at dosing events
            # Find periods where pump was active and measure result
            if pct_time_active > 1:  # Only if pump actually runs
                # Calculate sensor change rate
                sensor_diff = sensor.diff()

                # Correlate pump output with subsequent sensor change
                # Try different lag windows
                best_effectiveness = 0
                best_lag = 0
                best_corr = 0

                for lag in range(1, 16):  # 1-15 minute lags
                    shifted_diff = sensor_diff.shift(-lag)
                    valid = ~(pump.isna() | shifted_diff.isna())

                    if valid.sum() < 50:
                        continue

                    corr = pump[valid].corr(shifted_diff[valid])

                    if not np.isnan(corr) and abs(corr) > abs(best_corr):
                        best_corr = corr
                        best_lag = lag

                # Calculate effectiveness ratio during active periods
                # Sum of pump output vs sum of sensor change
                active_windows = self._find_dosing_windows(pump, active_threshold)

                if active_windows:
                    total_pump_output = 0
                    total_sensor_change = 0

                    for start, end in active_windows:
                        # Extend window to capture delayed response
                        response_end = min(end + 10, len(sensor) - 1)

                        window_pump = pump.iloc[start:end].sum()
                        window_sensor_start = sensor.iloc[start]
                        window_sensor_end = sensor.iloc[response_end]
                        window_change = window_sensor_end - window_sensor_start

                        if mapping.get('invert'):
                            window_change = -window_change

                        total_pump_output += window_pump
                        total_sensor_change += window_change

                    if total_pump_output > 0:
                        effectiveness = total_sensor_change / total_pump_output
                        metrics['effectiveness'] = {
                            'value': round(float(effectiveness), 6),
                            'unit': mapping['unit'],
                            'dosing_events_analyzed': len(active_windows),
                            'total_pump_output': round(float(total_pump_output), 1),
                            'total_sensor_change': round(float(total_sensor_change), 4),
                            'response_lag_minutes': best_lag,
                            'output_result_correlation': round(float(best_corr), 3)
                        }

                        # Flag potential issues
                        if abs(effectiveness) < 0.0001 and total_pump_output > 100:
                            metrics['red_flag'] = {
                                'issue': 'HIGH_OUTPUT_NO_RESULT',
                                'description': 'Pump running but no measured change',
                                'possible_causes': [
                                    'Empty chemical tank',
                                    'Blocked dosing line',
                                    'Pump failure',
                                    'Sensor fault'
                                ]
                            }
            else:
                metrics['effectiveness'] = {
                    'status': 'NOT_ACTIVE',
                    'description': f'Pump only active {pct_time_active}% of time'
                }

                # Check if sensor is still being maintained somehow
                sensor_std = sensor.std()
                if sensor_std > 0.1:
                    metrics['note'] = 'Sensor varies despite low pump activity - manual dosing?'

            pump_metrics[name] = metrics

        return pump_metrics

    def _find_dosing_windows(self, pump_series: pd.Series, threshold: float,
                             min_duration: int = 2, gap_tolerance: int = 3) -> list:
        """
        Find continuous dosing windows where pump is active.

        Returns list of (start_idx, end_idx) tuples.
        """
        active = pump_series > threshold
        windows = []

        in_window = False
        start_idx = 0
        gap_count = 0

        for i, is_active in enumerate(active):
            if is_active:
                if not in_window:
                    start_idx = i
                    in_window = True
                gap_count = 0
            else:
                if in_window:
                    gap_count += 1
                    if gap_count > gap_tolerance:
                        end_idx = i - gap_count
                        if end_idx - start_idx >= min_duration:
                            windows.append((start_idx, end_idx))
                        in_window = False

        # Close final window if still open
        if in_window:
            end_idx = len(active) - 1
            if end_idx - start_idx >= min_duration:
                windows.append((start_idx, end_idx))

        return windows

    def update_all_baselines(self, device_name: str = None, days_back: int = 14):
        """Update baselines for all pools."""
        if device_name:
            device_dirs = [self.chunks_dir / device_name]
        else:
            device_dirs = [d for d in self.chunks_dir.iterdir() if d.is_dir()]

        for device_dir in device_dirs:
            device = device_dir.name

            # Find all pools for this device
            pools = set()
            for db_file in device_dir.glob("*.db"):
                try:
                    conn = sqlite3.connect(str(db_file))
                    result = pd.read_sql_query(
                        "SELECT DISTINCT pool FROM readings", conn
                    )
                    conn.close()
                    pools.update(result['pool'].tolist())
                except:
                    pass

            for pool in pools:
                baseline = self.calculate_baseline(device, pool, days_back)
                if baseline:
                    if 'pools' not in self.baselines:
                        self.baselines['pools'] = {}

                    # Merge with existing baseline (preserve manual settings)
                    if pool in self.baselines['pools']:
                        existing = self.baselines['pools'][pool]
                        # Keep manual settings like pool_type, acceptable_range, etc.
                        for key in ['pool_type', 'anomaly_thresholds']:
                            if key in existing:
                                baseline[key] = existing[key]

                    self.baselines['pools'][pool] = baseline
                    logger.info(f"Updated baseline for {pool}")

        self._save_baselines()

    def check_deviations(self, device_name: str, pool_name: str,
                        current_data: pd.DataFrame = None,
                        hours_back: int = 1) -> list[DeviationAlert]:
        """
        Check current data against baseline and return any deviations.
        """
        if pool_name not in self.baselines.get('pools', {}):
            logger.warning(f"No baseline for {pool_name}")
            return []

        baseline = self.baselines['pools'][pool_name]
        alerts = []

        # Load recent data if not provided
        if current_data is None:
            current_data = self._load_pool_data(
                device_name, pool_name,
                days_back=hours_back/24
            )

        if current_data.empty:
            return alerts

        # Pivot current data
        pivoted = current_data.pivot_table(
            index='ts', columns='point_label', values='value', aggfunc='mean'
        )
        pivoted = pivoted.resample('1min').mean()

        thresholds = baseline.get('anomaly_thresholds', {
            'zscore_warning': 2.5,
            'zscore_alarm': 3.5
        })

        # Check each sensor against baseline
        for sensor, sensor_baseline in baseline.get('normal_operating_ranges', {}).items():
            if sensor not in pivoted.columns:
                continue

            current = pivoted[sensor].dropna()
            if current.empty:
                continue

            current_mean = current.mean()
            baseline_mean = sensor_baseline.get('mean', 0)
            baseline_std = sensor_baseline.get('std', 1)

            if baseline_std == 0:
                baseline_std = 0.01  # Avoid division by zero

            # Z-score check
            zscore = (current_mean - baseline_mean) / baseline_std

            if abs(zscore) > thresholds.get('zscore_alarm', 3.5):
                alerts.append(DeviationAlert(
                    pool=pool_name,
                    sensor=sensor,
                    alert_type='alarm',
                    category='value',
                    message=f"{sensor} significantly outside normal range",
                    current_value=round(current_mean, 4),
                    baseline_value=round(baseline_mean, 4),
                    deviation_amount=round(zscore, 2),
                    timestamp=datetime.now().isoformat()
                ))
            elif abs(zscore) > thresholds.get('zscore_warning', 2.5):
                alerts.append(DeviationAlert(
                    pool=pool_name,
                    sensor=sensor,
                    alert_type='warning',
                    category='value',
                    message=f"{sensor} outside normal range",
                    current_value=round(current_mean, 4),
                    baseline_value=round(baseline_mean, 4),
                    deviation_amount=round(zscore, 2),
                    timestamp=datetime.now().isoformat()
                ))

        # Check correlations
        baseline_corrs = baseline.get('established_correlations', {})

        if ('chlorine_orp' in baseline_corrs and
            'Chlorine_MeasuredValue' in pivoted.columns and
            'ORP_MeasuredValue' in pivoted.columns):

            cl = pivoted['Chlorine_MeasuredValue'].dropna()
            orp = pivoted['ORP_MeasuredValue'].dropna()
            common = cl.index.intersection(orp.index)

            if len(common) > 30:
                current_corr = cl[common].corr(orp[common])
                baseline_corr = baseline_corrs['chlorine_orp'].get('correlation', 0)

                diff = abs(current_corr - baseline_corr)

                if diff > 0.35:
                    alerts.append(DeviationAlert(
                        pool=pool_name,
                        sensor='Chlorine-ORP correlation',
                        alert_type='alarm',
                        category='correlation',
                        message="Chlorine-ORP relationship has changed significantly",
                        current_value=round(current_corr, 3),
                        baseline_value=round(baseline_corr, 3),
                        deviation_amount=round(diff, 3),
                        timestamp=datetime.now().isoformat()
                    ))
                elif diff > 0.20:
                    alerts.append(DeviationAlert(
                        pool=pool_name,
                        sensor='Chlorine-ORP correlation',
                        alert_type='warning',
                        category='correlation',
                        message="Chlorine-ORP relationship is drifting",
                        current_value=round(current_corr, 3),
                        baseline_value=round(baseline_corr, 3),
                        deviation_amount=round(diff, 3),
                        timestamp=datetime.now().isoformat()
                    ))

        return alerts

    def generate_deviation_report(self, alerts: list[DeviationAlert]) -> str:
        """Generate a human-readable deviation report."""
        if not alerts:
            return "No deviations detected."

        report = ["# Deviation Report", f"**Generated:** {datetime.now()}", ""]

        alarms = [a for a in alerts if a.alert_type == 'alarm']
        warnings = [a for a in alerts if a.alert_type == 'warning']

        if alarms:
            report.append("## ALARMS")
            for alert in alarms:
                report.append(f"- **{alert.pool}/{alert.sensor}**: {alert.message}")
                report.append(f"  - Current: {alert.current_value}, Baseline: {alert.baseline_value}")
                report.append(f"  - Deviation: {alert.deviation_amount}")
            report.append("")

        if warnings:
            report.append("## Warnings")
            for alert in warnings:
                report.append(f"- **{alert.pool}/{alert.sensor}**: {alert.message}")
                report.append(f"  - Current: {alert.current_value}, Baseline: {alert.baseline_value}")
            report.append("")

        return "\n".join(report)

    def save_deviation_history(self, alerts: list[DeviationAlert]):
        """Save deviations to history file."""
        history = []
        if self.deviations_file.exists():
            with open(self.deviations_file, 'r') as f:
                history = json.load(f)

        for alert in alerts:
            history.append({
                'pool': alert.pool,
                'sensor': alert.sensor,
                'alert_type': alert.alert_type,
                'category': alert.category,
                'message': alert.message,
                'current_value': alert.current_value,
                'baseline_value': alert.baseline_value,
                'deviation_amount': alert.deviation_amount,
                'timestamp': alert.timestamp
            })

        # Keep last 1000 entries
        history = history[-1000:]

        with open(self.deviations_file, 'w') as f:
            json.dump(history, f, indent=2)

    def get_baseline_summary(self, pool_name: str) -> str:
        """Get a human-readable summary of a pool's baseline."""
        if pool_name not in self.baselines.get('pools', {}):
            return f"No baseline for {pool_name}"

        b = self.baselines['pools'][pool_name]

        lines = [
            f"# {pool_name} Baseline Summary",
            f"**Last Updated:** {b.get('last_baseline_update', 'Unknown')}",
            f"**Data Points:** {b.get('data_points_in_baseline', 0):,}",
            ""
        ]

        ranges = b.get('normal_operating_ranges', {})
        if ranges:
            lines.append("## Normal Operating Ranges")
            for sensor, data in ranges.items():
                short_name = sensor.replace('_MeasuredValue', '')
                lines.append(
                    f"- **{short_name}**: {data.get('mean', 0):.2f} "
                    f"(p5={data.get('p5', 0):.2f}, p95={data.get('p95', 0):.2f})"
                )
            lines.append("")

        corrs = b.get('established_correlations', {})
        if corrs:
            lines.append("## Established Correlations")
            if 'chlorine_orp' in corrs:
                c = corrs['chlorine_orp']
                lines.append(
                    f"- **Chlorine->ORP**: r={c.get('correlation', 0):.3f}, "
                    f"slope={c.get('slope', 0):.1f} mV/(mg/L)"
                )
            if 'orp_ph' in corrs:
                c = corrs['orp_ph']
                lines.append(
                    f"- **pH->ORP**: r={c.get('correlation', 0):.3f}, "
                    f"slope={c.get('slope', 0):.1f} mV/pH"
                )
            lines.append("")

        # Pump effectiveness section
        pumps = b.get('pump_effectiveness', {})
        if pumps:
            lines.append("## Pump Effectiveness")
            for pump_name, data in pumps.items():
                activity = data.get('activity', {})
                effectiveness = data.get('effectiveness', {})
                red_flag = data.get('red_flag')

                lines.append(f"### {pump_name.upper()} Pump")
                lines.append(
                    f"- Activity: {activity.get('pct_time_active', 0):.1f}% of time, "
                    f"avg {activity.get('mean_when_active', 0):.1f}% when running"
                )

                if isinstance(effectiveness, dict) and 'value' in effectiveness:
                    lines.append(
                        f"- Effectiveness: {effectiveness.get('value', 0):.6f} {effectiveness.get('unit', '')}"
                    )
                    lines.append(
                        f"- Response lag: {effectiveness.get('response_lag_minutes', 0)} min, "
                        f"correlation: {effectiveness.get('output_result_correlation', 0):.3f}"
                    )
                    lines.append(
                        f"- Analyzed {effectiveness.get('dosing_events_analyzed', 0)} dosing events"
                    )
                elif isinstance(effectiveness, dict) and 'status' in effectiveness:
                    lines.append(f"- Status: {effectiveness.get('status')} - {effectiveness.get('description', '')}")

                if red_flag:
                    lines.append(f"- **RED FLAG**: {red_flag.get('issue')} - {red_flag.get('description')}")

                note = data.get('note')
                if note:
                    lines.append(f"- Note: {note}")

                lines.append("")

        return "\n".join(lines)


def main():
    """Run baseline manager."""
    import argparse

    parser = argparse.ArgumentParser(description='Manage pool baselines')
    parser.add_argument('--update', action='store_true', help='Update all baselines')
    parser.add_argument('--check', action='store_true', help='Check for deviations')
    parser.add_argument('--device', type=str, help='Specific device')
    parser.add_argument('--pool', type=str, help='Specific pool')
    parser.add_argument('--days', type=int, default=14, help='Days of data for baseline')
    parser.add_argument('--summary', action='store_true', help='Show baseline summary')
    args = parser.parse_args()

    manager = BaselineManager()

    if args.update:
        logger.info("Updating baselines...")
        manager.update_all_baselines(args.device, args.days)
        print("Baselines updated.")

    if args.check:
        logger.info("Checking for deviations...")
        if args.device and args.pool:
            alerts = manager.check_deviations(args.device, args.pool)
            report = manager.generate_deviation_report(alerts)
            print(report)
            if alerts:
                manager.save_deviation_history(alerts)
        else:
            print("Specify --device and --pool for deviation check")

    if args.summary:
        if args.pool:
            print(manager.get_baseline_summary(args.pool))
        else:
            for pool in manager.baselines.get('pools', {}).keys():
                print(manager.get_baseline_summary(pool))
                print("\n" + "="*50 + "\n")


if __name__ == '__main__':
    main()
