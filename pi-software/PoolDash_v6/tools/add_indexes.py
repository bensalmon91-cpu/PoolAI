#!/usr/bin/env python3
"""
Quick script to add performance indexes to PoolAIssistant database
No confirmations - just adds the indexes
"""

import sqlite3
import sys
from datetime import datetime

db_path = "/opt/PoolAIssistant/data/pool_readings.sqlite3"

print(f"Adding indexes to: {db_path}")
print()

try:
    con = sqlite3.connect(db_path, timeout=60)

    indexes = [
        ("idx_readings_pool_label_ts", "CREATE INDEX IF NOT EXISTS idx_readings_pool_label_ts ON readings(pool, point_label, ts)"),
        ("idx_readings_host", "CREATE INDEX IF NOT EXISTS idx_readings_host ON readings(host)"),
        ("idx_readings_ts_pool", "CREATE INDEX IF NOT EXISTS idx_readings_ts_pool ON readings(ts, pool)"),
    ]

    for idx_name, idx_sql in indexes:
        print(f"Creating index: {idx_name}...")
        start = datetime.now()
        con.execute(idx_sql)
        con.commit()
        elapsed = (datetime.now() - start).total_seconds()
        print(f"  ✓ Created in {elapsed:.1f}s")

    print("\nUpdating query planner statistics...")
    con.execute("ANALYZE")
    con.commit()
    print("  ✓ ANALYZE complete")

    con.close()

    print("\n✓ All indexes created successfully!")
    print("\nRestart services to apply:")
    print("  sudo systemctl restart poolaissistant_logger poolaissistant_ui")

except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)
