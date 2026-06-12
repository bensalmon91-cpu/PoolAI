"""Tests for the update-status cache logic in scripts/update_check.py.

The Settings/System pages render exclusively from the cached status file
(update_status.json) — never from the network — so the staleness rules and
the read/write roundtrip are what keep the UI honest. Everything here runs
without a network.
"""
from datetime import datetime, timedelta

from scripts import update_check


# ----------------------------
# is_status_stale_error
# ----------------------------

def test_empty_status_is_not_stale():
    assert update_check.is_status_stale_error({}) is False
    assert update_check.is_status_stale_error(None) is False


def test_ok_status_is_never_stale():
    status = {"status": "ok", "updated_at": "2020-01-01T00:00:00"}
    assert update_check.is_status_stale_error(status) is False


def test_fresh_error_is_not_stale():
    status = {
        "status": "error",
        "updated_at": datetime.now().isoformat(),
    }
    assert update_check.is_status_stale_error(status) is False


def test_old_error_is_stale():
    old = datetime.now() - timedelta(
        minutes=update_check.ERROR_CACHE_EXPIRY_MINUTES + 1
    )
    status = {"status": "error", "updated_at": old.isoformat()}
    assert update_check.is_status_stale_error(status) is True


def test_error_without_timestamp_is_stale():
    assert update_check.is_status_stale_error({"status": "error"}) is True


def test_error_with_unparseable_timestamp_is_stale():
    status = {"status": "error", "updated_at": "not-a-date"}
    assert update_check.is_status_stale_error(status) is True


# ----------------------------
# write_status / read_status roundtrip
# ----------------------------

def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(update_check, "STATUS_FILE", tmp_path / "update_status.json")

    update_check.write_status({
        "status": "ok",
        "message": "No updates available",
        "update_available": False,
    })
    status = update_check.read_status()

    assert status["status"] == "ok"
    assert status["update_available"] is False
    # write_status stamps the write time — the UI uses this for staleness.
    datetime.fromisoformat(status["updated_at"])


def test_read_status_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(update_check, "STATUS_FILE", tmp_path / "nope.json")
    assert update_check.read_status() == {}


def test_read_status_corrupt_file_returns_empty(tmp_path, monkeypatch):
    corrupt = tmp_path / "update_status.json"
    corrupt.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(update_check, "STATUS_FILE", corrupt)
    assert update_check.read_status() == {}
