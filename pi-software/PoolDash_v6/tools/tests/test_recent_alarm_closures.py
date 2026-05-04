"""Test get_recent_alarm_closures — the v6.11.12 path that propagates
alarm-end events with closed_reason to the cloud server."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make scripts/ importable.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _setup_db(tmp_path: Path) -> Path:
    """Build a SQLite DB with the v6.11.10 alarm_events schema (incl.
    closed_reason). This mirrors db_init in tools/modbus_logger.py — kept
    inline rather than importing modbus_logger to avoid pulling pymodbus
    into this test."""
    db = tmp_path / "pool_readings.sqlite3"
    con = sqlite3.connect(db)
    con.execute("""
        CREATE TABLE alarm_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_ts TEXT NOT NULL,
            ended_ts TEXT,
            pool TEXT NOT NULL,
            host TEXT NOT NULL,
            system_name TEXT,
            serial_number TEXT,
            source_label TEXT NOT NULL,
            bit_name TEXT NOT NULL,
            closed_reason TEXT
        );
    """)
    con.commit()
    con.close()
    return db


def _insert_alarm(db: Path, started_ts: str, ended_ts, closed_reason,
                  pool="PoolA", host="10.0.0.1", bit="b0"):
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO alarm_events(started_ts, ended_ts, pool, host, system_name, "
        "serial_number, source_label, bit_name, closed_reason) "
        "VALUES (?, ?, ?, ?, 'Sys', 'SN1', 'Status_X', ?, ?)",
        (started_ts, ended_ts, pool, host, bit, closed_reason),
    )
    con.commit()
    con.close()


def test_returns_recently_closed_with_closed_reason(tmp_path: Path) -> None:
    """The fundamental behaviour: a closure within window is returned
    with its closed_reason field intact."""
    import cloud_upload as cu
    db = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)

    _insert_alarm(db,
                  started_ts=_iso(now - timedelta(minutes=8)),
                  ended_ts=_iso(now - timedelta(minutes=2)),
                  closed_reason="controller_offline")

    rows = cu.get_recent_alarm_closures(db, since_minutes=10)

    assert len(rows) == 1
    r = rows[0]
    assert r["closed_reason"] == "controller_offline"
    assert r["source"] == "b0"
    assert r["pool"] == "PoolA"


def test_excludes_old_closures_outside_window(tmp_path: Path) -> None:
    """Closures older than the window must NOT be returned — otherwise
    every snapshot would re-send the entire history forever."""
    import cloud_upload as cu
    db = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)

    # Closure 30 min ago — outside the 10-minute window.
    _insert_alarm(db,
                  started_ts=_iso(now - timedelta(hours=2)),
                  ended_ts=_iso(now - timedelta(minutes=30)),
                  closed_reason=None)

    rows = cu.get_recent_alarm_closures(db, since_minutes=10)
    assert rows == []


def test_excludes_still_open_alarms(tmp_path: Path) -> None:
    """A row with ended_ts NULL is still active — must be excluded
    from the closures payload (active alarms go in alarms.active)."""
    import cloud_upload as cu
    db = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)

    _insert_alarm(db,
                  started_ts=_iso(now - timedelta(minutes=5)),
                  ended_ts=None,
                  closed_reason=None)

    rows = cu.get_recent_alarm_closures(db, since_minutes=10)
    assert rows == []


def test_preserves_null_closed_reason(tmp_path: Path) -> None:
    """A normal close (bit observed OFF) has closed_reason=NULL on the
    Pi side. The function must return that as None, not coerce to
    'observed_off' or empty string — server-side mapping does that."""
    import cloud_upload as cu
    db = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)

    _insert_alarm(db,
                  started_ts=_iso(now - timedelta(minutes=5)),
                  ended_ts=_iso(now - timedelta(minutes=1)),
                  closed_reason=None)

    rows = cu.get_recent_alarm_closures(db, since_minutes=10)
    assert len(rows) == 1
    assert rows[0]["closed_reason"] is None


def test_respects_limit(tmp_path: Path) -> None:
    """A Pi catching up after a long outage must not push thousands of
    closures in a single payload — the LIMIT cap protects the server."""
    import cloud_upload as cu
    db = _setup_db(tmp_path)
    now = datetime.now(timezone.utc)

    for i in range(20):
        _insert_alarm(db,
                      started_ts=_iso(now - timedelta(minutes=5)),
                      ended_ts=_iso(now - timedelta(seconds=60 - i)),
                      closed_reason=None,
                      bit=f"b{i}")

    rows = cu.get_recent_alarm_closures(db, since_minutes=10, limit=5)
    assert len(rows) == 5


def test_returns_empty_if_closed_reason_column_missing(tmp_path: Path) -> None:
    """If a Pi predates the v6.11.9 migration, alarm_events lacks the
    closed_reason column. The function must return [] rather than
    crashing — backwards compat for partial-rollout scenarios."""
    import cloud_upload as cu
    # Build a DB with the OLD schema (no closed_reason column).
    db = tmp_path / "pool_readings.sqlite3"
    con = sqlite3.connect(db)
    con.execute("""
        CREATE TABLE alarm_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_ts TEXT NOT NULL,
            ended_ts TEXT,
            pool TEXT NOT NULL,
            host TEXT NOT NULL,
            source_label TEXT NOT NULL,
            bit_name TEXT NOT NULL
        );
    """)
    con.execute(
        "INSERT INTO alarm_events(started_ts, ended_ts, pool, host, source_label, bit_name) "
        "VALUES ('2026-01-01T00:00:00', '2026-01-01T00:01:00', 'P', 'H', 'S', 'b0')"
    )
    con.commit(); con.close()

    rows = cu.get_recent_alarm_closures(db, since_minutes=10)
    assert rows == []


def test_returns_empty_if_db_does_not_exist(tmp_path: Path) -> None:
    import cloud_upload as cu
    db = tmp_path / "nonexistent.sqlite3"
    assert cu.get_recent_alarm_closures(db, since_minutes=10) == []
