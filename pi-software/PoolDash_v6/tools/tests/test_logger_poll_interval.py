"""Tests for modbus_logger.current_sample_seconds — the live poll-interval +
intensive-monitoring-window logic added in v6.11.15.

Pure function (takes a settings dict + now), so no hardware/network needed.
"""
from __future__ import annotations

import modbus_logger as ml


def test_normal_interval_used_when_no_intensive_window():
    s = {"logger_poll_interval_seconds": 30, "intensive_monitoring_until": 0}
    assert ml.current_sample_seconds(s, now=1000) == 30.0


def test_intensive_interval_used_while_window_active():
    s = {
        "logger_poll_interval_seconds": 30,
        "intensive_poll_interval_seconds": 5,
        "intensive_monitoring_until": 2000,
    }
    assert ml.current_sample_seconds(s, now=1000) == 5.0


def test_reverts_to_normal_after_window_expires():
    s = {
        "logger_poll_interval_seconds": 30,
        "intensive_poll_interval_seconds": 5,
        "intensive_monitoring_until": 500,  # in the past relative to now=1000
    }
    assert ml.current_sample_seconds(s, now=1000) == 30.0


def test_missing_keys_fall_back_to_sample_seconds():
    assert ml.current_sample_seconds({}, now=1000) == ml.SAMPLE_SECONDS


def test_non_dict_falls_back():
    assert ml.current_sample_seconds("not-a-dict", now=1000) == ml.SAMPLE_SECONDS


def test_zero_normal_interval_falls_back():
    # 0 is falsy -> treated as unset -> SAMPLE_SECONDS default.
    assert ml.current_sample_seconds({"logger_poll_interval_seconds": 0}, now=1000) == ml.SAMPLE_SECONDS


def test_floor_of_one_second():
    s = {"intensive_poll_interval_seconds": 0.5, "intensive_monitoring_until": 2000}
    assert ml.current_sample_seconds(s, now=1000) == 1.0


def test_garbage_values_fall_back():
    s = {"logger_poll_interval_seconds": "abc", "intensive_monitoring_until": "xyz"}
    assert ml.current_sample_seconds(s, now=1000) == ml.SAMPLE_SECONDS
