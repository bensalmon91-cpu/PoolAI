"""
PoolAIssistant Brain - Data Investigator
An agentic analysis system that lets Claude actively hunt through pool data,
form hypotheses, and interrogate the data to find hidden patterns.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import hashlib

import numpy as np
import pandas as pd
from scipy import stats
from anthropic import Anthropic
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('investigator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# DOMAIN KNOWLEDGE - Pool Chemistry & Control Systems Expertise
# =============================================================================

SYSTEM_PROMPT = """You are an expert pool/spa water chemistry analyst and control systems engineer with decades of experience. You have deep knowledge of:

## Water Chemistry Expertise
- **Chlorine dynamics**: Free chlorine (HOCl/OCl-) equilibrium, combined chlorine (chloramines), breakpoint chlorination
- **pH chemistry**: Carbonate buffering systems, CO2 effects, relationship between pH and chlorine efficacy
- **Temperature effects**: Henry's law for gas dissolution, reaction rate changes (Q10 rule), evaporation impacts
- **Cyanuric acid**: UV stabilization, chlorine lock phenomenon, optimal CYA:chlorine ratios
- **Alkalinity**: Total alkalinity vs carbonate alkalinity, Langelier Saturation Index
- **ORP (Oxidation-Reduction Potential)**: Relationship to free chlorine, interference factors

## Control Systems Knowledge
- **PID control**: Proportional, integral, derivative tuning for chemical dosing
- **Dead time/transport delay**: Time for chemicals to mix and sensors to respond
- **Sensor dynamics**: Response curves, calibration drift, interference effects
- **Dosing systems**: Peristaltic pumps, erosion feeders, gas injection, electrochlorination
- **Hysteresis**: Avoiding rapid on/off cycling, deadband settings

## Common Failure Modes
- Sensor fouling (biofilm, scale, chemical deposits)
- Pump failures (air locks, tubing wear, cavitation)
- Control instability (oscillation, overshoot, hunting)
- Chemical supply issues (empty tanks, clogged lines, expired chemicals)
- Plumbing issues (dead legs, stratification, poor mixing)

## Commercial Pool Requirements (UK/EU)
- Free chlorine: 0.5-2.0 mg/L (typically 1.0-1.5 for spas due to higher temps)
- Combined chlorine: <1.0 mg/L (ideally <0.5 mg/L)
- pH: 7.0-7.6 (optimal 7.2-7.4)
- Temperature: Pools 26-28°C, Spas 36-40°C
- Turnover times vary by pool type

## Investigation Mindset
When analyzing data, you think like a detective:
1. Look for anomalies that might indicate equipment issues
2. Check if sensor readings are physically plausible
3. Look for correlations that reveal causation
4. Consider time-of-day patterns (bather load, outdoor conditions)
5. Watch for gradual drift that might indicate calibration issues
6. Identify sudden changes that might indicate equipment events

You have access to tools that let you query the raw data. Use them to test hypotheses and drill down into suspicious patterns. Don't just accept the summary statistics - dig into the details.

When you find something suspicious, investigate further. Ask follow-up questions. Cross-reference with other sensors. Build a case before making conclusions.
"""

# =============================================================================
# Knowledge Base - Accumulates domain knowledge over time
# =============================================================================

class KnowledgeBase:
    """Stores and retrieves domain knowledge, equipment specs, and past insights."""

    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        self.equipment_file = self.knowledge_dir / 'equipment.json'
        self.insights_file = self.knowledge_dir / 'insights.json'
        self.history_file = self.knowledge_dir / 'investigation_history.json'
        self.parameters_file = self.knowledge_dir / 'optimal_parameters.json'

        self._init_files()

    def _init_files(self):
        """Initialize knowledge files if they don't exist."""
        defaults = {
            self.equipment_file: {
                'devices': {},
                'sensors': {},
                'dosing_systems': {},
                'last_updated': None
            },
            self.insights_file: {
                'patterns': [],
                'correlations': [],
                'recurring_issues': [],
                'last_updated': None
            },
            self.history_file: {
                'investigations': [],
                'total_count': 0
            },
            self.parameters_file: {
                'pools': {},
                'global_defaults': {
                    'chlorine': {'min': 0.5, 'max': 2.0, 'target': 1.0},
                    'pH': {'min': 7.0, 'max': 7.6, 'target': 7.2},
                    'temperature': {'min': 26, 'max': 40, 'target': 28},
                    'response_time_warning_minutes': 15,
                    'anomaly_threshold_zscore': 3.0
                }
            }
        }

        for file_path, default_content in defaults.items():
            if not file_path.exists():
                with open(file_path, 'w') as f:
                    json.dump(default_content, f, indent=2)

    def load(self, file_path: Path) -> dict:
        """Load a knowledge file."""
        with open(file_path, 'r') as f:
            return json.load(f)

    def save(self, file_path: Path, data: dict):
        """Save a knowledge file."""
        data['last_updated'] = datetime.now().isoformat()
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def add_insight(self, insight: dict):
        """Add a new insight to the knowledge base."""
        data = self.load(self.insights_file)
        insight['timestamp'] = datetime.now().isoformat()
        insight['id'] = hashlib.md5(json.dumps(insight, default=str).encode()).hexdigest()[:8]
        data['patterns'].append(insight)
        self.save(self.insights_file, data)
        logger.info(f"Added insight: {insight.get('title', 'Untitled')}")

    def add_investigation(self, investigation: dict):
        """Record a completed investigation."""
        data = self.load(self.history_file)
        investigation['timestamp'] = datetime.now().isoformat()
        investigation['id'] = data['total_count'] + 1
        data['investigations'].append(investigation)
        data['total_count'] += 1

        # Keep last 100 investigations
        if len(data['investigations']) > 100:
            data['investigations'] = data['investigations'][-100:]

        self.save(self.history_file, data)

    def get_relevant_history(self, pool_name: str = None, keywords: list = None) -> list:
        """Retrieve relevant past investigations."""
        data = self.load(self.history_file)
        investigations = data.get('investigations', [])

        if pool_name:
            investigations = [i for i in investigations if i.get('pool') == pool_name]

        if keywords:
            def matches(inv):
                text = json.dumps(inv).lower()
                return any(kw.lower() in text for kw in keywords)
            investigations = [i for i in investigations if matches(i)]

        return investigations[-10:]  # Return last 10 relevant

    def get_context_for_pool(self, device_name: str, pool_name: str) -> str:
        """Get accumulated knowledge context for a specific pool."""
        context_parts = []

        # Equipment info
        equipment = self.load(self.equipment_file)
        if device_name in equipment.get('devices', {}):
            context_parts.append(f"## Equipment Info\n{json.dumps(equipment['devices'][device_name], indent=2)}")

        # Optimal parameters
        params = self.load(self.parameters_file)
        pool_key = f"{device_name}/{pool_name}"
        if pool_key in params.get('pools', {}):
            context_parts.append(f"## Optimal Parameters for {pool_name}\n{json.dumps(params['pools'][pool_key], indent=2)}")
        else:
            context_parts.append(f"## Default Parameters\n{json.dumps(params['global_defaults'], indent=2)}")

        # Past insights
        insights = self.load(self.insights_file)
        relevant_patterns = [p for p in insights.get('patterns', [])
                           if pool_name in str(p) or device_name in str(p)][-5:]
        if relevant_patterns:
            context_parts.append(f"## Past Insights\n{json.dumps(relevant_patterns, indent=2)}")

        # Investigation history
        history = self.get_relevant_history(pool_name)
        if history:
            context_parts.append(f"## Recent Investigations\n{json.dumps(history, indent=2)}")

        return "\n\n".join(context_parts) if context_parts else "No prior knowledge for this pool."

    def update_equipment(self, device_name: str, equipment_info: dict):
        """Update equipment information for a device."""
        data = self.load(self.equipment_file)
        data['devices'][device_name] = equipment_info
        self.save(self.equipment_file, data)

    def update_optimal_parameters(self, device_name: str, pool_name: str, parameters: dict):
        """Update optimal parameters for a pool."""
        data = self.load(self.parameters_file)
        pool_key = f"{device_name}/{pool_name}"
        data['pools'][pool_key] = parameters
        self.save(self.parameters_file, data)


# =============================================================================
# Data Interrogator - Provides tools for Claude to query the data
# =============================================================================

class DataInterrogator:
    """Provides data query tools that Claude can use to investigate."""

    def __init__(self, chunks_dir: Path):
        self.chunks_dir = chunks_dir
        self._data_cache = {}

    def _get_device_data(self, device_name: str) -> pd.DataFrame:
        """Load and cache data for a device."""
        if device_name in self._data_cache:
            return self._data_cache[device_name]

        device_dir = self.chunks_dir / device_name
        if not device_dir.exists():
            return pd.DataFrame()

        all_dfs = []
        for db_file in device_dir.glob("*.db"):
            try:
                conn = sqlite3.connect(str(db_file))
                df = pd.read_sql_query("SELECT * FROM readings", conn)
                conn.close()
                df['ts'] = pd.to_datetime(df['ts'])
                all_dfs.append(df)
            except Exception as e:
                logger.debug(f"Error loading {db_file}: {e}")

        if not all_dfs:
            return pd.DataFrame()

        combined = pd.concat(all_dfs, ignore_index=True)
        combined = combined.sort_values('ts').drop_duplicates()
        self._data_cache[device_name] = combined
        return combined

    def get_available_data(self) -> dict:
        """Get summary of available data."""
        summary = {}
        for device_dir in self.chunks_dir.iterdir():
            if device_dir.is_dir():
                df = self._get_device_data(device_dir.name)
                if not df.empty:
                    summary[device_dir.name] = {
                        'pools': list(df['pool'].unique()),
                        'sensors': list(df['point_label'].unique()),
                        'date_range': {
                            'start': str(df['ts'].min()),
                            'end': str(df['ts'].max())
                        },
                        'total_readings': len(df)
                    }
        return summary

    # =========================================================================
    # Query Tools - These become Claude's investigation instruments
    # =========================================================================

    def query_time_range(self, device: str, pool: str, sensor: str,
                        start_time: str, end_time: str) -> dict:
        """Get sensor data for a specific time range."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        mask = (df['pool'] == pool) & (df['point_label'] == sensor)
        if start_time:
            mask &= df['ts'] >= pd.to_datetime(start_time)
        if end_time:
            mask &= df['ts'] <= pd.to_datetime(end_time)

        subset = df[mask].copy()
        if subset.empty:
            return {'error': 'No data matching criteria'}

        return {
            'sensor': sensor,
            'pool': pool,
            'count': len(subset),
            'time_range': {
                'start': str(subset['ts'].min()),
                'end': str(subset['ts'].max())
            },
            'statistics': {
                'mean': round(subset['value'].mean(), 4),
                'std': round(subset['value'].std(), 4),
                'min': round(subset['value'].min(), 4),
                'max': round(subset['value'].max(), 4)
            },
            'values': [
                {'time': str(row['ts']), 'value': round(row['value'], 4)}
                for _, row in subset.head(100).iterrows()
            ]
        }

    def query_sensor_comparison(self, device: str, pool: str,
                               sensor1: str, sensor2: str,
                               start_time: str = None, end_time: str = None) -> dict:
        """Compare two sensors over time."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        pool_df = df[df['pool'] == pool].copy()

        # Pivot to get both sensors as columns
        pivoted = pool_df.pivot_table(
            index='ts', columns='point_label', values='value', aggfunc='mean'
        )

        if sensor1 not in pivoted.columns or sensor2 not in pivoted.columns:
            return {'error': f'Sensor not found. Available: {list(pivoted.columns)[:20]}'}

        comparison = pivoted[[sensor1, sensor2]].dropna()

        if start_time:
            comparison = comparison[comparison.index >= pd.to_datetime(start_time)]
        if end_time:
            comparison = comparison[comparison.index <= pd.to_datetime(end_time)]

        if len(comparison) < 10:
            return {'error': 'Insufficient overlapping data'}

        # Calculate correlation
        corr = comparison[sensor1].corr(comparison[sensor2])

        # Calculate time-lagged correlation
        max_lag = min(30, len(comparison) // 4)
        best_lag = 0
        best_lag_corr = corr

        for lag in range(-max_lag, max_lag + 1):
            if lag == 0:
                continue
            s1 = comparison[sensor1].iloc[max(0, -lag):len(comparison) - max(0, lag)]
            s2 = comparison[sensor2].iloc[max(0, lag):len(comparison) - max(0, -lag)]
            if len(s1) > 10:
                lag_corr = s1.reset_index(drop=True).corr(s2.reset_index(drop=True))
                if abs(lag_corr) > abs(best_lag_corr):
                    best_lag_corr = lag_corr
                    best_lag = lag

        return {
            'sensor1': sensor1,
            'sensor2': sensor2,
            'pool': pool,
            'data_points': len(comparison),
            'correlation': round(corr, 4),
            'best_lag_correlation': round(best_lag_corr, 4),
            'best_lag_minutes': best_lag,
            'sensor1_stats': {
                'mean': round(comparison[sensor1].mean(), 4),
                'std': round(comparison[sensor1].std(), 4)
            },
            'sensor2_stats': {
                'mean': round(comparison[sensor2].mean(), 4),
                'std': round(comparison[sensor2].std(), 4)
            },
            'sample_data': [
                {
                    'time': str(idx),
                    sensor1: round(row[sensor1], 4),
                    sensor2: round(row[sensor2], 4)
                }
                for idx, row in comparison.head(50).iterrows()
            ]
        }

    def find_anomalies(self, device: str, pool: str, sensor: str,
                      threshold_zscore: float = 3.0,
                      window_minutes: int = 60) -> dict:
        """Find anomalous readings for a sensor."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        mask = (df['pool'] == pool) & (df['point_label'] == sensor)
        subset = df[mask].copy().set_index('ts').sort_index()

        if len(subset) < window_minutes * 2:
            return {'error': 'Insufficient data for anomaly detection'}

        # Calculate rolling statistics
        rolling_mean = subset['value'].rolling(f'{window_minutes}min').mean()
        rolling_std = subset['value'].rolling(f'{window_minutes}min').std()

        # Z-score
        z_scores = (subset['value'] - rolling_mean) / (rolling_std + 1e-10)

        # Find anomalies
        anomaly_mask = abs(z_scores) > threshold_zscore
        anomalies = subset[anomaly_mask].copy()
        anomalies['z_score'] = z_scores[anomaly_mask]
        anomalies['expected'] = rolling_mean[anomaly_mask]

        return {
            'sensor': sensor,
            'pool': pool,
            'threshold': threshold_zscore,
            'window_minutes': window_minutes,
            'total_readings': len(subset),
            'anomaly_count': len(anomalies),
            'anomaly_percentage': round(100 * len(anomalies) / len(subset), 4),
            'anomalies': [
                {
                    'time': str(idx),
                    'value': round(row['value'], 4),
                    'expected': round(row['expected'], 4),
                    'z_score': round(row['z_score'], 2),
                    'deviation': 'high' if row['z_score'] > 0 else 'low'
                }
                for idx, row in anomalies.head(50).iterrows()
            ]
        }

    def find_rapid_changes(self, device: str, pool: str, sensor: str,
                          threshold_percentile: float = 99) -> dict:
        """Find periods of unusually rapid change."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        mask = (df['pool'] == pool) & (df['point_label'] == sensor)
        subset = df[mask].copy().set_index('ts').sort_index()

        if len(subset) < 100:
            return {'error': 'Insufficient data'}

        # Calculate rate of change
        diff = subset['value'].diff()
        threshold = diff.abs().quantile(threshold_percentile / 100)

        rapid_changes = subset[diff.abs() > threshold].copy()
        rapid_changes['rate_of_change'] = diff[diff.abs() > threshold]

        return {
            'sensor': sensor,
            'pool': pool,
            'threshold_percentile': threshold_percentile,
            'threshold_value': round(threshold, 4),
            'rapid_change_count': len(rapid_changes),
            'changes': [
                {
                    'time': str(idx),
                    'value': round(row['value'], 4),
                    'change': round(row['rate_of_change'], 4),
                    'direction': 'increase' if row['rate_of_change'] > 0 else 'decrease'
                }
                for idx, row in rapid_changes.head(50).iterrows()
            ]
        }

    def get_hourly_pattern(self, device: str, pool: str, sensor: str) -> dict:
        """Analyze hourly patterns (time-of-day effects)."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        mask = (df['pool'] == pool) & (df['point_label'] == sensor)
        subset = df[mask].copy()
        subset['hour'] = subset['ts'].dt.hour

        hourly = subset.groupby('hour')['value'].agg(['mean', 'std', 'count'])

        return {
            'sensor': sensor,
            'pool': pool,
            'hourly_pattern': [
                {
                    'hour': int(hour),
                    'mean': round(row['mean'], 4),
                    'std': round(row['std'], 4),
                    'count': int(row['count'])
                }
                for hour, row in hourly.iterrows()
            ],
            'peak_hour': int(hourly['mean'].idxmax()),
            'low_hour': int(hourly['mean'].idxmin()),
            'peak_value': round(hourly['mean'].max(), 4),
            'low_value': round(hourly['mean'].min(), 4)
        }

    def check_setpoint_tracking(self, device: str, pool: str,
                               measurement: str, setpoint: str) -> dict:
        """Analyze how well a measurement tracks its setpoint."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        pool_df = df[df['pool'] == pool].copy()
        pivoted = pool_df.pivot_table(
            index='ts', columns='point_label', values='value', aggfunc='mean'
        )

        if measurement not in pivoted.columns or setpoint not in pivoted.columns:
            return {'error': 'Sensors not found'}

        tracking = pivoted[[measurement, setpoint]].dropna()

        if len(tracking) < 100:
            return {'error': 'Insufficient data'}

        # Calculate error
        error = tracking[measurement] - tracking[setpoint]
        abs_error = error.abs()

        # Time above/below setpoint
        above = (error > 0).sum()
        below = (error < 0).sum()

        return {
            'measurement': measurement,
            'setpoint': setpoint,
            'pool': pool,
            'data_points': len(tracking),
            'setpoint_value': round(tracking[setpoint].mean(), 4),
            'measurement_mean': round(tracking[measurement].mean(), 4),
            'mean_error': round(error.mean(), 4),
            'mean_absolute_error': round(abs_error.mean(), 4),
            'max_overshoot': round(error.max(), 4),
            'max_undershoot': round(error.min(), 4),
            'time_above_setpoint_pct': round(100 * above / len(tracking), 2),
            'time_below_setpoint_pct': round(100 * below / len(tracking), 2),
            'error_std': round(error.std(), 4)
        }

    def correlate_with_all(self, device: str, pool: str,
                          target_sensor: str, min_correlation: float = 0.3) -> dict:
        """Find all sensors correlated with a target sensor."""
        df = self._get_device_data(device)
        if df.empty:
            return {'error': f'No data for device {device}'}

        pool_df = df[df['pool'] == pool].copy()
        pivoted = pool_df.pivot_table(
            index='ts', columns='point_label', values='value', aggfunc='mean'
        )

        if target_sensor not in pivoted.columns:
            return {'error': f'Sensor {target_sensor} not found'}

        target = pivoted[target_sensor].dropna()
        correlations = []

        for sensor in pivoted.columns:
            if sensor == target_sensor:
                continue
            try:
                other = pivoted[sensor].dropna()
                common = target.index.intersection(other.index)
                if len(common) < 100:
                    continue

                corr = target[common].corr(other[common])
                if abs(corr) >= min_correlation:
                    correlations.append({
                        'sensor': sensor,
                        'correlation': round(corr, 4),
                        'direction': 'positive' if corr > 0 else 'negative',
                        'strength': 'strong' if abs(corr) > 0.7 else 'moderate' if abs(corr) > 0.5 else 'weak'
                    })
            except:
                continue

        # Sort by absolute correlation
        correlations.sort(key=lambda x: abs(x['correlation']), reverse=True)

        return {
            'target_sensor': target_sensor,
            'pool': pool,
            'min_correlation': min_correlation,
            'correlated_sensors': correlations[:20]  # Top 20
        }


# =============================================================================
# Investigation Agent - The main agentic loop
# =============================================================================

class InvestigationAgent:
    """Runs an agentic investigation loop where Claude hunts for issues."""

    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.output_dir = Path(os.getenv('OUTPUT_DIR', './output'))
        self.chunks_dir = Path(os.getenv('LOCAL_CHUNKS_DIR', './data/chunks'))
        # Knowledge files stored at root level for git tracking
        self.knowledge_dir = Path('./knowledge')
        self.reports_dir = self.output_dir / 'investigations'
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.knowledge = KnowledgeBase(self.knowledge_dir)
        self.interrogator = DataInterrogator(self.chunks_dir)

        if self.api_key:
            self.client = Anthropic(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("ANTHROPIC_API_KEY not set. Investigation disabled.")

        # Define tools that Claude can use
        self.tools = [
            {
                "name": "query_time_range",
                "description": "Get sensor data for a specific time range. Use this to examine specific periods of interest.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "Device name (e.g., 'Swanwood_Spa')"},
                        "pool": {"type": "string", "description": "Pool name (e.g., 'Vitality', 'Main')"},
                        "sensor": {"type": "string", "description": "Sensor name (e.g., 'Chlorine_MeasuredValue')"},
                        "start_time": {"type": "string", "description": "Start time in ISO format"},
                        "end_time": {"type": "string", "description": "End time in ISO format"}
                    },
                    "required": ["device", "pool", "sensor"]
                }
            },
            {
                "name": "compare_sensors",
                "description": "Compare two sensors to find correlations and lag relationships.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "pool": {"type": "string"},
                        "sensor1": {"type": "string", "description": "First sensor to compare"},
                        "sensor2": {"type": "string", "description": "Second sensor to compare"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"}
                    },
                    "required": ["device", "pool", "sensor1", "sensor2"]
                }
            },
            {
                "name": "find_anomalies",
                "description": "Find anomalous readings that deviate significantly from the norm.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "pool": {"type": "string"},
                        "sensor": {"type": "string"},
                        "threshold_zscore": {"type": "number", "default": 3.0, "description": "Z-score threshold for anomaly detection"},
                        "window_minutes": {"type": "integer", "default": 60, "description": "Rolling window size in minutes"}
                    },
                    "required": ["device", "pool", "sensor"]
                }
            },
            {
                "name": "find_rapid_changes",
                "description": "Find periods of unusually rapid change in a sensor.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "pool": {"type": "string"},
                        "sensor": {"type": "string"},
                        "threshold_percentile": {"type": "number", "default": 99}
                    },
                    "required": ["device", "pool", "sensor"]
                }
            },
            {
                "name": "get_hourly_pattern",
                "description": "Analyze time-of-day patterns for a sensor (bather load, outdoor effects).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "pool": {"type": "string"},
                        "sensor": {"type": "string"}
                    },
                    "required": ["device", "pool", "sensor"]
                }
            },
            {
                "name": "check_setpoint_tracking",
                "description": "Analyze how well a measured value tracks its setpoint (control system performance).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "pool": {"type": "string"},
                        "measurement": {"type": "string", "description": "The measured value sensor"},
                        "setpoint": {"type": "string", "description": "The setpoint sensor"}
                    },
                    "required": ["device", "pool", "measurement", "setpoint"]
                }
            },
            {
                "name": "correlate_with_all",
                "description": "Find all sensors that correlate with a target sensor.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "pool": {"type": "string"},
                        "target_sensor": {"type": "string"},
                        "min_correlation": {"type": "number", "default": 0.3}
                    },
                    "required": ["device", "pool", "target_sensor"]
                }
            },
            {
                "name": "record_finding",
                "description": "Record an important finding or insight to the knowledge base.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Brief title for the finding"},
                        "category": {"type": "string", "enum": ["anomaly", "correlation", "equipment_issue", "water_quality", "control_issue", "pattern"]},
                        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "description": {"type": "string", "description": "Detailed description of the finding"},
                        "evidence": {"type": "string", "description": "Data evidence supporting this finding"},
                        "recommendation": {"type": "string", "description": "Recommended action"}
                    },
                    "required": ["title", "category", "severity", "description"]
                }
            }
        ]

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return the result."""
        try:
            if tool_name == "query_time_range":
                result = self.interrogator.query_time_range(**tool_input)
            elif tool_name == "compare_sensors":
                result = self.interrogator.query_sensor_comparison(
                    tool_input['device'], tool_input['pool'],
                    tool_input['sensor1'], tool_input['sensor2'],
                    tool_input.get('start_time'), tool_input.get('end_time')
                )
            elif tool_name == "find_anomalies":
                result = self.interrogator.find_anomalies(
                    tool_input['device'], tool_input['pool'], tool_input['sensor'],
                    tool_input.get('threshold_zscore', 3.0),
                    tool_input.get('window_minutes', 60)
                )
            elif tool_name == "find_rapid_changes":
                result = self.interrogator.find_rapid_changes(
                    tool_input['device'], tool_input['pool'], tool_input['sensor'],
                    tool_input.get('threshold_percentile', 99)
                )
            elif tool_name == "get_hourly_pattern":
                result = self.interrogator.get_hourly_pattern(**tool_input)
            elif tool_name == "check_setpoint_tracking":
                result = self.interrogator.check_setpoint_tracking(**tool_input)
            elif tool_name == "correlate_with_all":
                result = self.interrogator.correlate_with_all(
                    tool_input['device'], tool_input['pool'],
                    tool_input['target_sensor'],
                    tool_input.get('min_correlation', 0.3)
                )
            elif tool_name == "record_finding":
                self.knowledge.add_insight(tool_input)
                result = {"status": "Finding recorded successfully", "finding": tool_input}
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def investigate(self, device_name: str = None, pool_name: str = None,
                   focus_area: str = None, max_iterations: int = 15) -> dict:
        """
        Run an investigation with Claude actively hunting for issues.

        Args:
            device_name: Specific device to investigate (or None for all)
            pool_name: Specific pool to investigate (or None for all)
            focus_area: Optional focus (e.g., "chlorine control", "anomalies", "correlations")
            max_iterations: Maximum number of tool-use iterations

        Returns:
            Investigation report with findings
        """
        if not self.client:
            return {"error": "ANTHROPIC_API_KEY not configured"}

        # Get available data summary
        available = self.interrogator.get_available_data()
        if not available:
            return {"error": "No data available. Run db_sync.py and analyzer.py first."}

        # Build initial context
        context_parts = [
            f"## Available Data\n```json\n{json.dumps(available, indent=2)}\n```"
        ]

        # Add prior knowledge if investigating specific pool
        if device_name and pool_name:
            prior = self.knowledge.get_context_for_pool(device_name, pool_name)
            context_parts.append(f"## Prior Knowledge\n{prior}")

        # Load existing analysis if available
        analysis_path = self.output_dir / 'analysis' / 'full_analysis.json'
        if analysis_path.exists():
            with open(analysis_path, 'r') as f:
                analysis = json.load(f)
            # Truncate for context
            analysis_summary = json.dumps(analysis, indent=2, default=str)[:30000]
            context_parts.append(f"## Pre-computed Analysis Summary\n```json\n{analysis_summary}\n```")

        context = "\n\n".join(context_parts)

        # Build the investigation prompt
        if focus_area:
            focus_instruction = f"Focus your investigation on: {focus_area}"
        else:
            focus_instruction = "Conduct a comprehensive investigation looking for any issues."

        if device_name and pool_name:
            target = f"Investigate device '{device_name}', pool '{pool_name}'."
        elif device_name:
            target = f"Investigate all pools on device '{device_name}'."
        else:
            target = "Investigate all available pools."

        user_prompt = f"""{context}

## Investigation Task

{target}

{focus_instruction}

As an expert investigator, you should:
1. Start by reviewing the pre-computed analysis for obvious issues
2. Form hypotheses about potential problems
3. Use the query tools to test your hypotheses
4. Drill down into any suspicious patterns
5. Cross-reference findings with other sensors
6. Record important findings using the record_finding tool
7. Build a comprehensive case for any issues you find

Be thorough but efficient. Follow leads. If something looks suspicious, investigate it.
When you've completed your investigation, provide a final summary of your findings."""

        messages = [{"role": "user", "content": user_prompt}]

        logger.info(f"Starting investigation: {target}")
        logger.info(f"Max iterations: {max_iterations}")

        investigation_log = []
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Investigation iteration {iteration}/{max_iterations}")

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=self.tools,
                messages=messages
            )

            # Process response
            assistant_content = []
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    investigation_log.append({
                        "iteration": iteration,
                        "type": "thinking",
                        "content": block.text
                    })
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })

                    logger.info(f"  Tool call: {block.name}")
                    result = self._execute_tool(block.name, block.input)

                    investigation_log.append({
                        "iteration": iteration,
                        "type": "tool_call",
                        "tool": block.name,
                        "input": block.input,
                        "result": json.loads(result) if result.startswith('{') else result
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # Check if we're done (no more tool calls)
            if response.stop_reason == "end_turn" and not tool_results:
                break

        # Extract final summary
        final_summary = ""
        for block in response.content:
            if block.type == "text":
                final_summary = block.text
                break

        # Build investigation report
        report = {
            "investigation_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "device": device_name or "all",
            "pool": pool_name or "all",
            "focus_area": focus_area,
            "iterations": iteration,
            "findings_recorded": len([l for l in investigation_log if l.get('tool') == 'record_finding']),
            "summary": final_summary,
            "log": investigation_log,
            "timestamp": datetime.now().isoformat()
        }

        # Save investigation
        self.knowledge.add_investigation({
            "device": device_name,
            "pool": pool_name,
            "focus": focus_area,
            "summary": final_summary[:500],  # Truncate for storage
            "findings_count": report['findings_recorded']
        })

        # Save full report
        report_path = self.reports_dir / f"investigation_{report['investigation_id']}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"Investigation saved: {report_path}")

        # Also save markdown report
        md_report = self._generate_markdown_report(report)
        md_path = self.reports_dir / f"investigation_{report['investigation_id']}.md"
        with open(md_path, 'w') as f:
            f.write(md_report)
        logger.info(f"Markdown report: {md_path}")

        return report

    def _generate_markdown_report(self, report: dict) -> str:
        """Generate a human-readable markdown report."""
        md = f"""# Pool Investigation Report

**Investigation ID:** {report['investigation_id']}
**Generated:** {report['timestamp']}
**Device:** {report['device']}
**Pool:** {report['pool']}
**Focus Area:** {report['focus_area'] or 'Comprehensive'}
**Iterations:** {report['iterations']}
**Findings Recorded:** {report['findings_recorded']}

---

## Summary

{report['summary']}

---

## Investigation Log

"""
        for entry in report['log']:
            if entry['type'] == 'thinking':
                md += f"### Iteration {entry['iteration']} - Analysis\n\n{entry['content']}\n\n"
            elif entry['type'] == 'tool_call':
                md += f"**Tool:** `{entry['tool']}`\n"
                md += f"**Input:** `{json.dumps(entry['input'])}`\n\n"

        md += """
---

*Report generated by PoolAIssistant Brain Investigation Agent*
"""
        return md

    def hunt(self, suspects: list = None) -> dict:
        """
        Hunt mode - actively look for specific types of issues.

        Args:
            suspects: List of things to look for, e.g.:
                     ["chlorine instability", "sensor drift", "dosing lag",
                      "temperature anomalies", "pH oscillation"]
        """
        if suspects is None:
            suspects = [
                "chlorine control issues",
                "pH instability",
                "sensor anomalies",
                "slow response times",
                "unusual correlations",
                "equipment problems"
            ]

        focus_description = "Hunt for: " + ", ".join(suspects)
        return self.investigate(focus_area=focus_description, max_iterations=20)


def main():
    """Run an investigation."""
    import argparse

    parser = argparse.ArgumentParser(description='Investigate pool data with Claude')
    parser.add_argument('--device', type=str, help='Specific device to investigate')
    parser.add_argument('--pool', type=str, help='Specific pool to investigate')
    parser.add_argument('--focus', type=str, help='Focus area for investigation')
    parser.add_argument('--hunt', action='store_true', help='Run in hunt mode')
    parser.add_argument('--max-iterations', type=int, default=15, help='Max investigation iterations')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PoolAIssistant Brain - Investigation Agent Starting")
    logger.info("=" * 60)

    agent = InvestigationAgent()

    if args.hunt:
        logger.info("Running in HUNT mode - actively searching for issues")
        report = agent.hunt()
    else:
        report = agent.investigate(
            device_name=args.device,
            pool_name=args.pool,
            focus_area=args.focus,
            max_iterations=args.max_iterations
        )

    if 'error' in report:
        print(f"\nError: {report['error']}")
    else:
        print(f"\n{'=' * 60}")
        print("INVESTIGATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Iterations: {report['iterations']}")
        print(f"Findings recorded: {report['findings_recorded']}")
        print(f"\n{report['summary']}")


if __name__ == '__main__':
    main()
