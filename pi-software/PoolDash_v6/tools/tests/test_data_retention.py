"""Tests for the set-based, budgeted thinning in scripts/data_cleanup.py.

The original implementation deleted each hour-group with a
strftime()-matched WHERE (non-indexable -> one full table scan per group),
so on a multi-GB production DB the nightly service was killed at
TimeoutStartSec every run and retention silently never happened
(discovered 2026-07-18: cleanup_state.json had never been written).

These tests pin the rewrite's contract:
- days past hourly retention collapse straight to one daily_avg row per
  (pool, host, point_label), preserving the mean
- days between full and hourly retention collapse to hourly_avg rows
- recent days are untouched, rows past daily retention are deleted
- a second run is a no-op (idempotent)
- an exhausted time budget stops work; the next run resumes from the
  cursors in cleanup_state.json and finishes
- --dry-run changes nothing and does not advance cursors
"""
from datetime import date, datetime, time as dtime, timedelta, timezone
import json
import sqlite3

import pytest

from scripts import data_cleanup as dc

POOLS = [("Spa", "192.168.200.12"), ("Plunge", "192.168.200.14")]
LABELS = ["pH_Value", "ORP_Value"]
ROWS_PER_COMBO = 144  # one reading every 10 minutes
N_COMBOS = len(POOLS) * len(LABELS)
EXPECTED_AVG = sum(range(ROWS_PER_COMBO)) / ROWS_PER_COMBO

DAY_AGES = {"ancient": 400, "old": 100, "mid": 50, "recent": 5}


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Synthetic readings DB with one day in each retention zone."""
    db_path = tmp_path / "pool_readings.sqlite3"
    con = sqlite3.connect(db_path)
    con.execute(
        """CREATE TABLE readings (
            ts TEXT NOT NULL, pool TEXT NOT NULL, host TEXT NOT NULL,
            system_name TEXT, serial_number TEXT, point_label TEXT NOT NULL,
            value REAL, raw_type TEXT)"""
    )
    rows = []
    for age in DAY_AGES.values():
        day = date.today() - timedelta(days=age)
        for pool, host in POOLS:
            for label in LABELS:
                for i in range(ROWS_PER_COMBO):
                    ts = datetime.combine(day, dtime(0, 0), tzinfo=timezone.utc) \
                        + timedelta(minutes=10 * i)
                    # logger-style ISO ts: '2026-04-15T00:10:00+00:00'
                    rows.append((ts.isoformat(), pool, host, "sys", "sn",
                                 label, float(i), "f32"))
    con.executemany("INSERT INTO readings VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()

    monkeypatch.setattr(dc, "POOL_DB_PATH", db_path)
    monkeypatch.setattr(dc, "CLEANUP_STATE_PATH", tmp_path / "cleanup_state.json")
    monkeypatch.setattr(dc, "SETTINGS_PATH", tmp_path / "missing_settings.json")
    return db_path


def day_rows(db_path, age_days):
    day = date.today() - timedelta(days=age_days)
    lo, hi = day.isoformat(), (day + timedelta(days=1)).isoformat()
    con = sqlite3.connect(db_path)
    try:
        count, avg = con.execute(
            "SELECT COUNT(*), AVG(value) FROM readings WHERE ts >= ? AND ts < ?",
            (lo, hi)).fetchone()
        types = sorted(r[0] for r in con.execute(
            "SELECT DISTINCT raw_type FROM readings WHERE ts >= ? AND ts < ?",
            (lo, hi)))
    finally:
        con.close()
    return count, types, avg


def run(**kwargs):
    assert dc.run_cleanup(dict(dc.DEFAULTS), **kwargs) is True


def test_full_pass_thins_each_zone(db):
    run()

    count, types, _ = day_rows(db, DAY_AGES["ancient"])
    assert count == 0  # aggregated then deleted by the 365d cutoff

    count, types, avg = day_rows(db, DAY_AGES["old"])
    assert (count, types) == (N_COMBOS, ["daily_avg"])
    assert avg == pytest.approx(EXPECTED_AVG)

    count, types, avg = day_rows(db, DAY_AGES["mid"])
    assert (count, types) == (24 * N_COMBOS, ["hourly_avg"])
    assert avg == pytest.approx(EXPECTED_AVG)

    count, types, _ = day_rows(db, DAY_AGES["recent"])
    assert (count, types) == (ROWS_PER_COMBO * N_COMBOS, ["f32"])

    state = json.loads(dc.CLEANUP_STATE_PATH.read_text())
    assert "hourly_thinned_until" in state and "daily_thinned_until" in state


def test_second_run_is_noop(db):
    run()
    before = {k: day_rows(db, v) for k, v in DAY_AGES.items()}
    run()
    assert {k: day_rows(db, v) for k, v in DAY_AGES.items()} == before


def test_budget_exhaustion_resumes_next_run(db, capsys):
    run(budget_seconds=0)
    assert "Time budget reached" in capsys.readouterr().out
    _, types, _ = day_rows(db, DAY_AGES["old"])
    assert types == ["f32"]  # nothing thinned under a zero budget

    run()  # resumes from cursors and finishes
    assert day_rows(db, DAY_AGES["old"])[1] == ["daily_avg"]
    assert day_rows(db, DAY_AGES["mid"])[1] == ["hourly_avg"]


def test_dry_run_changes_nothing(db):
    run(dry_run=True)
    for name, age in DAY_AGES.items():
        count, types, _ = day_rows(db, age)
        assert (count, types) == (ROWS_PER_COMBO * N_COMBOS, ["f32"]), name
    if dc.CLEANUP_STATE_PATH.exists():
        state = json.loads(dc.CLEANUP_STATE_PATH.read_text())
        assert "daily_thinned_until" not in state
