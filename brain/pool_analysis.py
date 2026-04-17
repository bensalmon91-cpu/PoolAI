import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import json
import warnings
warnings.filterwarnings("ignore")

class PoolAnalyzer:
    def __init__(self, db_path="output/pool_readings.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.key_sensors = ["pH_MeasuredValue", "Temp_MeasuredValue", "ORP_MeasuredValue"]
        self.results = {}

    def load_pool_data(self, pool, sensor):
        query = "SELECT ts, value FROM readings WHERE pool = ? AND point_label = ? ORDER BY ts"
        df = pd.read_sql_query(query, self.conn, params=[pool, sensor])
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.drop_duplicates(subset=["ts"], keep="first")
        df = df.set_index("ts").sort_index()
        return df

    def calculate_baselines(self, df):
        if df.empty:
            return None
        values = df["value"].dropna()
        long_term = {
            "mean": float(values.mean()), "std": float(values.std()),
            "median": float(values.median()), "min": float(values.min()),
            "max": float(values.max()), "q25": float(values.quantile(0.25)),
            "q75": float(values.quantile(0.75)), "count": int(len(values))
        }
        hourly = df.resample("1h").mean()
        rolling_6h = hourly["value"].rolling(window=6, min_periods=3).mean()
        rolling_24h = hourly["value"].rolling(window=24, min_periods=12).mean()
        daily = df.resample("1D").agg({"value": ["mean", "std", "min", "max", "count"]})
        daily.columns = ["mean", "std", "min", "max", "count"]
        daily_baselines = []
        for date, row in daily.iterrows():
            if pd.notna(row["mean"]):
                daily_baselines.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "mean": round(float(row["mean"]), 3),
                    "std": round(float(row["std"]), 3) if pd.notna(row["std"]) else 0,
                    "min": round(float(row["min"]), 3),
                    "max": round(float(row["max"]), 3),
                    "count": int(row["count"])
                })
        return {"long_term": long_term, "daily": daily_baselines, "rolling_6h": rolling_6h, "rolling_24h": rolling_24h, "hourly": hourly}

    def detect_change_points(self, df, baselines):
        if df.empty or baselines is None:
            return []
        events = []
        lt = baselines["long_term"]
        mean, std = lt["mean"], lt["std"]
        if std == 0:
            return events
        hourly = baselines["hourly"].copy()
        hourly["z_score"] = (hourly["value"] - mean) / std
        hourly["deviation"] = abs(hourly["z_score"]) > 2
        hourly["group"] = (hourly["deviation"] != hourly["deviation"].shift()).cumsum()
        for gid, gdf in hourly[hourly["deviation"]].groupby("group"):
            if len(gdf) >= 3:
                events.append({
                    "type": "sustained_deviation",
                    "start": gdf.index[0].strftime("%Y-%m-%d %H:%M"),
                    "end": gdf.index[-1].strftime("%Y-%m-%d %H:%M"),
                    "duration_hours": len(gdf),
                    "direction": "HIGH" if gdf["value"].mean() > mean else "LOW",
                    "avg_value": round(float(gdf["value"].mean()), 3),
                    "baseline_mean": round(mean, 3),
                    "deviation_percent": round(((gdf["value"].mean() - mean) / mean) * 100, 1)
                })
        r6h = baselines["rolling_6h"].dropna()
        if len(r6h) > 2:
            shifts = r6h.diff().abs()
            threshold = 2 * std
            for ts, shift in shifts[shifts > threshold].items():
                events.append({"type": "sudden_shift", "time": ts.strftime("%Y-%m-%d %H:%M"), "magnitude": round(float(shift), 3), "threshold": round(float(threshold), 3)})
        events.sort(key=lambda x: x.get("start", x.get("time", "")))
        return events

    def analyze_pool(self, pool):
        print(f"Analyzing: {pool}")
        pool_results = {"pool": pool, "analysis_time": datetime.now().isoformat(), "sensors": {}}
        for sensor in self.key_sensors:
            sname = sensor.replace("_MeasuredValue", "")
            print(f"  {sname}...")
            df = self.load_pool_data(pool, sensor)
            print(f"    {len(df):,} readings")
            if df.empty:
                continue
            baselines = self.calculate_baselines(df)
            events = self.detect_change_points(df, baselines)
            pool_results["sensors"][sname] = {
                "long_term_baseline": baselines["long_term"],
                "daily_baselines": baselines["daily"],
                "events": events,
                "event_count": len(events)
            }
            lt = baselines["long_term"]
            print(f"    mean={lt['mean']:.3f}, std={lt['std']:.3f}")
            print(f"    Events: {len(events)}")
        return pool_results

    def analyze_all_pools(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT pool FROM readings ORDER BY pool")
        pools = [r[0] for r in cursor.fetchall()]
        print(f"Found {len(pools)} pools")
        self.results = {"analysis_metadata": {"generated": datetime.now().isoformat()}, "pools": {}}
        for pool in pools:
            self.results["pools"][pool] = self.analyze_pool(pool)
        return self.results

    def generate_report(self, output_dir="analysis"):
        Path(output_dir).mkdir(exist_ok=True)
        json_path = Path(output_dir) / "pool_baselines.json"
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"JSON saved: {json_path}")
        return json_path

    def close(self):
        self.conn.close()

if __name__ == "__main__":
    a = PoolAnalyzer()
    try:
        a.analyze_all_pools()
        a.generate_report()
        print("Complete!")
    finally:
        a.close()