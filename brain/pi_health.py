"""
Read the latest device_health heartbeat per Pi from Hostinger MySQL.

Provides the per-Pi context that brain's staleness alarm (B1) lacks:
  - heartbeat_age_hours — how long since the Pi last phoned home
  - upload_age_hours — how long since the Pi successfully uploaded a chunk
  - pending_chunks — chunks queued on the Pi waiting to upload

This lets the alert checker discriminate between failure modes that all
look the same to B1 ("data is stale"):
  - Pi offline:          heartbeat is old → physical/network problem
  - chunker stuck:       heartbeat fresh, pending_chunks > 0 → service issue
  - genuinely quiet:     heartbeat fresh, pending_chunks = 0 → no work, fine

DB credentials come from the consolidated root .env via load_dotenv() walking
up the tree. If MySQL is unreachable the function returns a sentinel dict
with `_error` set — the alert checker treats that as a soft warning, not a
hard failure (a 30-second DB blip shouldn't fail the whole sync pipeline).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# A Pi that hasn't sent a heartbeat in this many hours is treated as offline.
# Pis usually heartbeat every 5-15 minutes (per the Pi-software cron); 2h
# is a comfortable margin above transient network blips without being
# numb to actual outages.
HEARTBEAT_OFFLINE_HOURS = float(os.getenv("HEARTBEAT_OFFLINE_HOURS", "2"))


def fetch_pi_health() -> dict:
    """Return {pis: [...]} with one entry per active Pi, OR {error: '...'}.

    Each Pi entry has:
      device_id, device_name, software_version,
      heartbeat_at (ISO str or None), heartbeat_age_hours (float or None),
      upload_at, upload_age_hours,
      pending_chunks, failed_uploads, is_offline (bool),
      offline_threshold_hours
    """
    try:
        import mysql.connector
    except ImportError:
        return {"error": "mysql.connector not installed (`pip install mysql-connector-python`)"}

    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 3306)),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            connection_timeout=10,
        )
    except Exception as e:
        return {"error": f"DB connection failed: {e}"}

    try:
        cur = conn.cursor(dictionary=True)
        # Latest heartbeat per active Pi. LEFT JOIN keeps Pis that have never
        # heartbeated — those show up as missing-data, which is its own signal.
        cur.execute("""
            SELECT d.id            AS device_id,
                   d.name          AS device_name,
                   h.ts            AS heartbeat_at,
                   h.last_upload_success,
                   h.pending_chunks,
                   h.failed_uploads,
                   h.software_version
            FROM pi_devices d
            LEFT JOIN device_health h ON h.id = (
                SELECT id FROM device_health
                WHERE device_id = d.id
                ORDER BY id DESC
                LIMIT 1
            )
            WHERE d.is_active = 1
            ORDER BY d.id
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"error": f"DB query failed: {e}"}

    now = datetime.now(timezone.utc)
    pis: list[dict] = []
    for r in rows:
        hb_at, hb_age = _ts_and_age(r["heartbeat_at"], now)
        up_at, up_age = _ts_and_age(r["last_upload_success"], now)
        is_offline = (hb_age is None) or (hb_age > HEARTBEAT_OFFLINE_HOURS)
        pis.append({
            "device_id": r["device_id"],
            "device_name": r["device_name"],
            "software_version": r.get("software_version"),
            "heartbeat_at": hb_at,
            "heartbeat_age_hours": hb_age,
            "upload_at": up_at,
            "upload_age_hours": up_age,
            "pending_chunks": r.get("pending_chunks"),
            "failed_uploads": r.get("failed_uploads"),
            "is_offline": is_offline,
            "offline_threshold_hours": HEARTBEAT_OFFLINE_HOURS,
        })

    return {"pis": pis}


def _ts_and_age(ts, now):
    """Return (iso_string_or_None, age_hours_or_None) for a maybe-None timestamp."""
    if ts is None:
        return None, None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_h = (now - ts).total_seconds() / 3600.0
    return ts.isoformat(), round(age_h, 2)


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_pi_health(), indent=2))
