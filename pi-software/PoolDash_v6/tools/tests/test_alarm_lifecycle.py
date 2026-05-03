"""Unit tests for the alarm-row lifecycle helpers in modbus_logger.

Pins down the contract introduced in v6.11.9 / v6.11.10:
- close_alarms_at_startup closes every open row with closed_reason='logger_restart'
- db_close_alarms_for_offline_controllers closes open rows whose source
  controller has been offline past the threshold (measured against
  last_success_ts, not last_failure_ts), leaves online and fresh-offline
  controllers' rows alone, and is idempotent on repeated invocation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import modbus_logger as ml


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    ml.db_init(con)
    return con


def _insert_open_alarm(con: sqlite3.Connection, host: str, started_ts: str, bit: str = "b0") -> int:
    cur = con.execute(
        "INSERT INTO alarm_events(started_ts, ended_ts, pool, host, system_name, "
        "serial_number, source_label, bit_name) VALUES (?, NULL, ?, ?, ?, ?, ?, ?)",
        (started_ts, "PoolA", host, "Sys", "SN1", "Status_X", bit),
    )
    con.commit()
    return cur.lastrowid


def _insert_health(
    con: sqlite3.Connection,
    host: str,
    status: str,
    last_success_ts: str | None,
    last_failure_ts: str | None,
) -> None:
    con.execute(
        "INSERT INTO controller_health(host, pool, status, last_success_ts, "
        "last_failure_ts, updated_ts) VALUES (?, ?, ?, ?, ?, ?)",
        (host, "PoolA", status, last_success_ts, last_failure_ts, _iso(_now())),
    )
    con.commit()


# ---------------------------------------------------------------------------
# close_alarms_at_startup
# ---------------------------------------------------------------------------

def test_startup_clear_closes_open_rows_and_leaves_closed_rows_alone() -> None:
    con = _fresh_db()
    now = _now()

    open_id_1 = _insert_open_alarm(con, "10.0.0.1", _iso(now - timedelta(minutes=5)))
    open_id_2 = _insert_open_alarm(con, "10.0.0.2", _iso(now - timedelta(minutes=2)), bit="b1")

    # An already-closed row must NOT be touched (closed naturally before reboot).
    closed_ts = _iso(now - timedelta(hours=1))
    cur = con.execute(
        "INSERT INTO alarm_events(started_ts, ended_ts, pool, host, system_name, "
        "serial_number, source_label, bit_name, closed_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (_iso(now - timedelta(hours=2)), closed_ts, "PoolA", "10.0.0.3",
         "Sys", "SN1", "Status_X", "b0"),
    )
    closed_id = cur.lastrowid
    con.commit()

    n = ml.close_alarms_at_startup(con)

    assert n == 2

    rows = {
        rid: (ended_ts, closed_reason)
        for rid, ended_ts, closed_reason in con.execute(
            "SELECT id, ended_ts, closed_reason FROM alarm_events ORDER BY id"
        )
    }

    # Both originally-open rows are now closed with the startup reason.
    assert rows[open_id_1][0] is not None
    assert rows[open_id_1][1] == "logger_restart"
    assert rows[open_id_2][0] is not None
    assert rows[open_id_2][1] == "logger_restart"

    # The pre-closed row is untouched: same ended_ts, closed_reason still NULL.
    assert rows[closed_id] == (closed_ts, None)


def test_startup_clear_is_idempotent_when_no_rows_open() -> None:
    con = _fresh_db()
    n1 = ml.close_alarms_at_startup(con)
    n2 = ml.close_alarms_at_startup(con)
    assert n1 == 0
    assert n2 == 0


# ---------------------------------------------------------------------------
# db_close_alarms_for_offline_controllers
# ---------------------------------------------------------------------------

def test_sweep_closes_only_past_threshold_offline_rows() -> None:
    con = _fresh_db()
    now = _now()

    # host A: offline 45 min — last_success was 45 min ago. Should be closed.
    _insert_health(con, "10.0.0.1", "offline",
                   last_success_ts=_iso(now - timedelta(minutes=45)),
                   last_failure_ts=_iso(now))  # last_failure bumped recently
    a_id = _insert_open_alarm(con, "10.0.0.1", _iso(now - timedelta(minutes=46)))

    # host B: offline only 10 min — under threshold. Must stay open.
    _insert_health(con, "10.0.0.2", "offline",
                   last_success_ts=_iso(now - timedelta(minutes=10)),
                   last_failure_ts=_iso(now))
    b_id = _insert_open_alarm(con, "10.0.0.2", _iso(now - timedelta(minutes=11)))

    # host C: online — sweep must never touch its rows even if last_success_ts is old.
    _insert_health(con, "10.0.0.3", "online",
                   last_success_ts=_iso(now - timedelta(hours=2)),
                   last_failure_ts=_iso(now - timedelta(hours=3)))
    c_id = _insert_open_alarm(con, "10.0.0.3", _iso(now - timedelta(hours=2)))

    n = ml.db_close_alarms_for_offline_controllers(con, threshold_minutes=30)

    assert n == 1

    by_id = {
        rid: (ended_ts, closed_reason)
        for rid, ended_ts, closed_reason in con.execute(
            "SELECT id, ended_ts, closed_reason FROM alarm_events"
        )
    }

    # Only host A's row was closed, and with the offline reason.
    assert by_id[a_id][0] is not None
    assert by_id[a_id][1] == "controller_offline"

    # host B (under threshold) and host C (online) untouched.
    assert by_id[b_id] == (None, None)
    assert by_id[c_id] == (None, None)


def test_sweep_is_idempotent() -> None:
    con = _fresh_db()
    now = _now()

    _insert_health(con, "10.0.0.1", "offline",
                   last_success_ts=_iso(now - timedelta(minutes=45)),
                   last_failure_ts=_iso(now))
    _insert_open_alarm(con, "10.0.0.1", _iso(now - timedelta(minutes=46)))

    n1 = ml.db_close_alarms_for_offline_controllers(con, threshold_minutes=30)
    n2 = ml.db_close_alarms_for_offline_controllers(con, threshold_minutes=30)

    assert n1 == 1
    assert n2 == 0  # already-closed rows are not re-closed


def test_sweep_skips_controllers_with_null_last_success_ts() -> None:
    # A controller that has never been online (e.g. wrong IP from day one)
    # has last_success_ts = NULL. Such a row has no genuine alarm history to
    # clean up, so the sweep must skip it rather than close on NULL math.
    con = _fresh_db()
    now = _now()

    _insert_health(con, "10.0.0.1", "offline",
                   last_success_ts=None,
                   last_failure_ts=_iso(now - timedelta(hours=24)))
    aid = _insert_open_alarm(con, "10.0.0.1", _iso(now - timedelta(hours=24)))

    n = ml.db_close_alarms_for_offline_controllers(con, threshold_minutes=30)

    assert n == 0
    row = con.execute(
        "SELECT ended_ts, closed_reason FROM alarm_events WHERE id = ?", (aid,)
    ).fetchone()
    assert row == (None, None)


# ---------------------------------------------------------------------------
# Regression: the v6.11.10 fix
# ---------------------------------------------------------------------------

def test_sweep_uses_last_success_ts_not_last_failure_ts() -> None:
    # Reproduces the v6.11.9 bug. With backoff capped at 60s, an offline
    # controller's last_failure_ts tracks "now within the last minute" forever.
    # The sweep must measure against last_success_ts (frozen at offline-onset)
    # so the threshold actually trips after 30 minutes.
    con = _fresh_db()
    now = _now()

    # Controller offline for an hour. last_success_ts froze 1h ago.
    # last_failure_ts updates every poll, so it's near-now.
    _insert_health(con, "10.0.0.1", "offline",
                   last_success_ts=_iso(now - timedelta(hours=1)),
                   last_failure_ts=_iso(now - timedelta(seconds=5)))
    _insert_open_alarm(con, "10.0.0.1", _iso(now - timedelta(hours=1)))

    n = ml.db_close_alarms_for_offline_controllers(con, threshold_minutes=30)

    # If the SQL still used last_failure_ts, n would be 0 (5 seconds < 30 min).
    # With the v6.11.10 fix using last_success_ts, n == 1.
    assert n == 1
