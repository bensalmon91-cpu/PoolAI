"""
PoolAIssistant Brain - Data Analyzer
Performs minute-level analysis on pool sensor data to find correlations,
response times, anomalies, and trends.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import correlate
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('analyzer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PoolDataAnalyzer:
    """Analyzes pool sensor data for correlations, trends, and anomalies."""

    def __init__(self, chunks_dir: Path = None):
        load_dotenv()
        self.chunks_dir = chunks_dir or Path(os.getenv('LOCAL_CHUNKS_DIR', './data/chunks'))
        self.output_dir = Path(os.getenv('OUTPUT_DIR', './output'))
        self.analysis_dir = self.output_dir / 'analysis'
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

    def load_chunk_to_dataframe(self, db_path: Path) -> pd.DataFrame:
        """Load a SQLite chunk into a pandas DataFrame."""
        try:
            conn = sqlite3.connect(str(db_path))
            df = pd.read_sql_query("SELECT * FROM readings", conn)
            conn.close()

            # Parse timestamp
            df['ts'] = pd.to_datetime(df['ts'])
            df = df.sort_values('ts')

            logger.info(f"Loaded {len(df):,} rows from {db_path.name}")
            return df
        except Exception as e:
            logger.error(f"Failed to load {db_path}: {e}")
            return pd.DataFrame()

    def load_all_chunks(self, device_dir: Path) -> pd.DataFrame:
        """Load all chunks for a device into a single DataFrame."""
        all_dfs = []

        for gz_file in device_dir.glob("*.db"):
            df = self.load_chunk_to_dataframe(gz_file)
            if not df.empty:
                all_dfs.append(df)

        if not all_dfs:
            return pd.DataFrame()

        combined = pd.concat(all_dfs, ignore_index=True)
        combined = combined.sort_values('ts').drop_duplicates()
        logger.info(f"Combined {len(combined):,} total rows")
        return combined

    def pivot_by_sensor(self, df: pd.DataFrame, pool_name: str) -> pd.DataFrame:
        """Pivot data to have sensors as columns, time as index."""
        pool_df = df[df['pool'] == pool_name].copy()

        # Pivot: timestamp as index, point_label as columns, value as values
        pivoted = pool_df.pivot_table(
            index='ts',
            columns='point_label',
            values='value',
            aggfunc='mean'  # Handle duplicates
        )

        # Resample to 1-minute intervals, forward fill gaps
        pivoted = pivoted.resample('1min').mean()

        return pivoted

    def calculate_cross_correlations(self, df: pd.DataFrame, max_lag_minutes: int = 30) -> dict:
        """
        Calculate cross-correlations between all sensor pairs.
        Finds which sensors lead/lag others and by how much.
        """
        correlations = {}
        sensors = df.columns.tolist()

        # Focus on key measurement sensors
        key_sensors = [s for s in sensors if any(k in s for k in
            ['MeasuredValue', 'Yout', 'Setpoint'])]

        if len(key_sensors) < 2:
            return correlations

        logger.info(f"Calculating cross-correlations for {len(key_sensors)} sensors...")

        for i, sensor1 in enumerate(key_sensors):
            for sensor2 in key_sensors[i+1:]:
                try:
                    s1 = df[sensor1].dropna()
                    s2 = df[sensor2].dropna()

                    # Align the series
                    common_idx = s1.index.intersection(s2.index)
                    if len(common_idx) < 100:
                        continue

                    s1 = s1[common_idx].values
                    s2 = s2[common_idx].values

                    # Normalize
                    s1 = (s1 - np.mean(s1)) / (np.std(s1) + 1e-10)
                    s2 = (s2 - np.mean(s2)) / (np.std(s2) + 1e-10)

                    # Cross-correlation
                    correlation = correlate(s1, s2, mode='full')
                    correlation = correlation / len(s1)

                    # Find lag with max correlation
                    mid = len(correlation) // 2
                    lag_range = min(max_lag_minutes, mid)
                    search_region = correlation[mid - lag_range:mid + lag_range + 1]

                    max_idx = np.argmax(np.abs(search_region))
                    optimal_lag = max_idx - lag_range
                    max_corr = search_region[max_idx]

                    if abs(max_corr) > 0.3:  # Only significant correlations
                        pair_name = f"{sensor1} vs {sensor2}"
                        correlations[pair_name] = {
                            'correlation': round(float(max_corr), 4),
                            'lag_minutes': int(optimal_lag),
                            'interpretation': self._interpret_correlation(
                                sensor1, sensor2, max_corr, optimal_lag
                            )
                        }
                except Exception as e:
                    logger.debug(f"Error correlating {sensor1} vs {sensor2}: {e}")

        return correlations

    def _interpret_correlation(self, s1: str, s2: str, corr: float, lag: int) -> str:
        """Generate human-readable interpretation of correlation."""
        strength = "strong" if abs(corr) > 0.7 else "moderate" if abs(corr) > 0.5 else "weak"
        direction = "positive" if corr > 0 else "negative"

        if lag == 0:
            timing = "simultaneously"
        elif lag > 0:
            timing = f"{s1} leads {s2} by {abs(lag)} minutes"
        else:
            timing = f"{s2} leads {s1} by {abs(lag)} minutes"

        return f"{strength} {direction} correlation; {timing}"

    def calculate_response_times(self, df: pd.DataFrame) -> dict:
        """
        Detect response times between control outputs and measured values.
        E.g., when chlorine dosing activates, how long until chlorine level rises?
        """
        responses = {}

        # Define control-measurement pairs
        pairs = [
            ('Chlorine_Yout', 'Chlorine_MeasuredValue', 'Chlorine dosing response'),
            ('pH_Yout', 'pH_MeasuredValue', 'pH dosing response'),
            ('Ch4_Yout', 'Ch4_MeasuredValue', 'Ch4 dosing response'),
        ]

        for control, measurement, description in pairs:
            if control not in df.columns or measurement not in df.columns:
                continue

            try:
                ctrl = df[control].dropna()
                meas = df[measurement].dropna()

                common_idx = ctrl.index.intersection(meas.index)
                if len(common_idx) < 100:
                    continue

                ctrl = ctrl[common_idx]
                meas = meas[common_idx]

                # Find moments where control output changes significantly
                ctrl_diff = ctrl.diff().abs()
                threshold = ctrl_diff.quantile(0.95)
                change_points = ctrl_diff[ctrl_diff > threshold].index

                response_times = []
                for change_time in change_points[:100]:  # Sample up to 100 events
                    # Look for corresponding change in measurement within 30 min
                    window_start = change_time
                    window_end = change_time + timedelta(minutes=30)

                    meas_window = meas[window_start:window_end]
                    if len(meas_window) < 5:
                        continue

                    # Find when measurement starts changing
                    meas_diff = meas_window.diff().abs()
                    meas_threshold = meas_diff.quantile(0.8)
                    response_points = meas_diff[meas_diff > meas_threshold]

                    if not response_points.empty:
                        response_time = (response_points.index[0] - change_time).total_seconds() / 60
                        if 0 < response_time < 30:
                            response_times.append(response_time)

                if response_times:
                    responses[description] = {
                        'avg_response_minutes': round(np.mean(response_times), 2),
                        'min_response_minutes': round(np.min(response_times), 2),
                        'max_response_minutes': round(np.max(response_times), 2),
                        'std_dev': round(np.std(response_times), 2),
                        'sample_count': len(response_times)
                    }
            except Exception as e:
                logger.debug(f"Error calculating response for {description}: {e}")

        return responses

    def detect_anomalies(self, df: pd.DataFrame, window_minutes: int = 60) -> dict:
        """
        Detect anomalies using rolling statistics.
        Flags readings that deviate significantly from recent patterns.
        """
        anomalies = {}

        key_sensors = [s for s in df.columns if 'MeasuredValue' in s]

        for sensor in key_sensors:
            try:
                series = df[sensor].dropna()
                if len(series) < window_minutes * 2:
                    continue

                # Rolling mean and std
                rolling_mean = series.rolling(window=window_minutes, center=True).mean()
                rolling_std = series.rolling(window=window_minutes, center=True).std()

                # Z-score
                z_scores = (series - rolling_mean) / (rolling_std + 1e-10)

                # Flag anomalies (|z| > 3)
                anomaly_mask = np.abs(z_scores) > 3
                anomaly_points = series[anomaly_mask]

                if len(anomaly_points) > 0:
                    anomalies[sensor] = {
                        'count': len(anomaly_points),
                        'percentage': round(100 * len(anomaly_points) / len(series), 4),
                        'timestamps': [str(t) for t in anomaly_points.index[:20]],  # First 20
                        'values': [round(v, 4) for v in anomaly_points.values[:20]],
                        'severity': 'high' if len(anomaly_points) / len(series) > 0.01 else 'low'
                    }
            except Exception as e:
                logger.debug(f"Error detecting anomalies for {sensor}: {e}")

        return anomalies

    def calculate_trends(self, df: pd.DataFrame) -> dict:
        """
        Calculate minute-level trends and rate of change.
        """
        trends = {}

        key_sensors = [s for s in df.columns if 'MeasuredValue' in s]

        for sensor in key_sensors:
            try:
                series = df[sensor].dropna()
                if len(series) < 100:
                    continue

                # Overall trend (linear regression)
                x = np.arange(len(series))
                slope, intercept, r_value, p_value, std_err = stats.linregress(x, series.values)

                # Rate of change per minute
                rate_of_change = series.diff()
                avg_rate = rate_of_change.mean()
                max_increase = rate_of_change.max()
                max_decrease = rate_of_change.min()

                # Volatility (std of rate of change)
                volatility = rate_of_change.std()

                trends[sensor] = {
                    'overall_trend': 'increasing' if slope > 0 else 'decreasing',
                    'slope_per_minute': round(float(slope), 6),
                    'r_squared': round(float(r_value ** 2), 4),
                    'avg_rate_of_change': round(float(avg_rate), 6),
                    'max_increase_per_minute': round(float(max_increase), 4),
                    'max_decrease_per_minute': round(float(max_decrease), 4),
                    'volatility': round(float(volatility), 6),
                    'current_value': round(float(series.iloc[-1]), 4),
                    'period_start_value': round(float(series.iloc[0]), 4),
                    'total_change': round(float(series.iloc[-1] - series.iloc[0]), 4)
                }
            except Exception as e:
                logger.debug(f"Error calculating trends for {sensor}: {e}")

        return trends

    def calculate_statistics(self, df: pd.DataFrame) -> dict:
        """Calculate comprehensive statistics for each sensor."""
        statistics = {}

        for sensor in df.columns:
            try:
                series = df[sensor].dropna()
                if len(series) < 10:
                    continue

                statistics[sensor] = {
                    'count': len(series),
                    'mean': round(float(series.mean()), 4),
                    'std': round(float(series.std()), 4),
                    'min': round(float(series.min()), 4),
                    'max': round(float(series.max()), 4),
                    'median': round(float(series.median()), 4),
                    'percentile_5': round(float(series.quantile(0.05)), 4),
                    'percentile_95': round(float(series.quantile(0.95)), 4),
                    'range': round(float(series.max() - series.min()), 4)
                }
            except Exception as e:
                logger.debug(f"Error calculating stats for {sensor}: {e}")

        return statistics

    def analyze_pool(self, df: pd.DataFrame, pool_name: str, device_name: str) -> dict:
        """Run full analysis on a single pool."""
        logger.info(f"Analyzing pool: {pool_name} at {device_name}")

        # Pivot data for time-series analysis
        pivoted = self.pivot_by_sensor(df, pool_name)

        if pivoted.empty:
            logger.warning(f"No data for pool {pool_name}")
            return {}

        logger.info(f"  Data range: {pivoted.index.min()} to {pivoted.index.max()}")
        logger.info(f"  Sensors: {len(pivoted.columns)}")
        logger.info(f"  Time points: {len(pivoted):,}")

        analysis = {
            'metadata': {
                'pool_name': pool_name,
                'device_name': device_name,
                'analysis_timestamp': datetime.now().isoformat(),
                'data_start': str(pivoted.index.min()),
                'data_end': str(pivoted.index.max()),
                'total_minutes': len(pivoted),
                'sensors_analyzed': len(pivoted.columns)
            },
            'statistics': self.calculate_statistics(pivoted),
            'trends': self.calculate_trends(pivoted),
            'cross_correlations': self.calculate_cross_correlations(pivoted),
            'response_times': self.calculate_response_times(pivoted),
            'anomalies': self.detect_anomalies(pivoted)
        }

        # Generate summary insights
        analysis['summary'] = self._generate_summary(analysis)

        return analysis

    def _generate_summary(self, analysis: dict) -> dict:
        """Generate a human-readable summary of key findings."""
        summary = {
            'key_findings': [],
            'concerns': [],
            'recommendations': []
        }

        # Check correlations
        strong_corrs = {k: v for k, v in analysis.get('cross_correlations', {}).items()
                       if abs(v['correlation']) > 0.7}
        if strong_corrs:
            summary['key_findings'].append(
                f"Found {len(strong_corrs)} strong sensor correlations"
            )

        # Check response times
        responses = analysis.get('response_times', {})
        for name, data in responses.items():
            if data['avg_response_minutes'] > 10:
                summary['concerns'].append(
                    f"{name}: Average response time is {data['avg_response_minutes']:.1f} minutes"
                )

        # Check anomalies
        high_anomalies = {k: v for k, v in analysis.get('anomalies', {}).items()
                         if v['severity'] == 'high'}
        if high_anomalies:
            summary['concerns'].append(
                f"High anomaly rate detected in {len(high_anomalies)} sensors"
            )

        # Check trends
        for sensor, trend in analysis.get('trends', {}).items():
            if abs(trend['total_change']) > 0.5:  # Significant change
                summary['key_findings'].append(
                    f"{sensor}: Changed by {trend['total_change']:.2f} over analysis period"
                )

        return summary

    def analyze_all(self) -> dict:
        """Analyze all available data."""
        results = {}

        # Find all extracted chunk directories
        for device_dir in self.chunks_dir.iterdir():
            if not device_dir.is_dir():
                continue

            device_name = device_dir.name
            logger.info(f"Processing device: {device_name}")

            # Load all data for this device
            df = self.load_all_chunks(device_dir)
            if df.empty:
                continue

            # Get unique pools
            pools = df['pool'].unique()
            results[device_name] = {}

            for pool_name in pools:
                analysis = self.analyze_pool(df, pool_name, device_name)
                if analysis:
                    results[device_name][pool_name] = analysis

                    # Save individual pool analysis
                    pool_dir = self.analysis_dir / device_name
                    pool_dir.mkdir(parents=True, exist_ok=True)

                    output_path = pool_dir / f"{pool_name}_analysis.json"
                    with open(output_path, 'w') as f:
                        json.dump(analysis, f, indent=2, default=str)
                    logger.info(f"  Saved: {output_path}")

        return results


def main():
    """Run the analyzer."""
    logger.info("=" * 50)
    logger.info("PoolAIssistant Brain - Data Analyzer Starting")
    logger.info("=" * 50)

    analyzer = PoolDataAnalyzer()
    results = analyzer.analyze_all()

    if results:
        # Save combined results
        output_path = analyzer.analysis_dir / 'full_analysis.json'
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Saved full analysis: {output_path}")

        logger.info("=" * 50)
        logger.info("Analysis complete!")
        logger.info("=" * 50)
    else:
        logger.warning("No data to analyze. Run db_sync.py first to download chunks.")


if __name__ == '__main__':
    main()
