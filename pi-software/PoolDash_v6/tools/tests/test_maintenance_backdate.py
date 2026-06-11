"""Unit tests for backdated maintenance entries (v6.11.13).

Pins down the log_action timestamp contract:
- blank timestamp logs at the current time (pre-v6.11.13 behaviour)
- a past timestamp is stored verbatim and sorts into the right place
  (last_entry/fetch_all order by timestamp, not insertion order)
- a future timestamp is rejected (block on physical impossibility only;
  arbitrarily old dates are allowed)
- a malformed timestamp is rejected
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from pooldash_app.db import maintenance as mdb

FMT = "%Y-%m-%d %H:%M:%S"


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "maintenance_test.sqlite3")


def test_blank_timestamp_logs_now(db_path):
    before = datetime.now().replace(microsecond=0)
    mdb.log_action(db_path, "PoolA", "Backwash")
    after = datetime.now().replace(microsecond=0)

    ts, _ = mdb.last_entry(db_path, "PoolA", "Backwash")
    assert before <= datetime.strptime(ts, FMT) <= after


def test_backdated_entry_stored_verbatim(db_path):
    past = (datetime.now() - timedelta(days=7)).strftime(FMT)
    mdb.log_action(db_path, "PoolA", "Backwash", note="last week", timestamp=past)

    ts, note = mdb.last_entry(db_path, "PoolA", "Backwash")
    assert ts == past
    assert note == "last week"


def test_backdated_entry_does_not_shadow_newer_entry(db_path):
    mdb.log_action(db_path, "PoolA", "Backwash", note="today")
    past = (datetime.now() - timedelta(days=3)).strftime(FMT)
    mdb.log_action(db_path, "PoolA", "Backwash", note="three days ago", timestamp=past)

    # last_entry must still report the newer row even though the backdated
    # row was inserted later (ordering is by timestamp, not rowid)
    _, note = mdb.last_entry(db_path, "PoolA", "Backwash")
    assert note == "today"

    # and fetch_all returns newest-first
    rows = mdb.fetch_all(db_path, "PoolA")
    assert [r["note"] for r in rows] == ["today", "three days ago"]


def test_arbitrarily_old_timestamp_allowed(db_path):
    ancient = "2020-01-01 09:00:00"
    mdb.log_action(db_path, "PoolA", "Backwash", timestamp=ancient)
    ts, _ = mdb.last_entry(db_path, "PoolA", "Backwash")
    assert ts == ancient


def test_future_timestamp_rejected(db_path):
    future = (datetime.now() + timedelta(hours=1)).strftime(FMT)
    with pytest.raises(ValueError, match="future"):
        mdb.log_action(db_path, "PoolA", "Backwash", timestamp=future)
    assert mdb.fetch_all(db_path, "PoolA") == []


def test_malformed_timestamp_rejected(db_path):
    with pytest.raises(ValueError, match="Invalid timestamp"):
        mdb.log_action(db_path, "PoolA", "Backwash", timestamp="last tuesday")
    with pytest.raises(ValueError, match="Invalid timestamp"):
        # datetime-local raw format must be normalized by the route first
        mdb.log_action(db_path, "PoolA", "Backwash", timestamp="2026-06-10T14:30")
    assert mdb.fetch_all(db_path, "PoolA") == []
