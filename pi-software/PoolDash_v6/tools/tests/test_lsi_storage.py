"""Unit tests for LSI history storage (v6.11.22 fix).

Pins down a real production bug: lsi_from_values() returns an LSIResult
frozen dataclass, not a dict, so main_ui.py's old lsi_result.get("lsi", 0) /
lsi_result.get("pH_saturation") calls raised AttributeError on every single
calculation - silently swallowed by a broad except, so lsi_readings was
never once written to on Swanwood. These tests exercise the real
calculator -> storage round trip (the same call shape main_ui.py uses)
against a real sqlite file, plus a regression guard on the dataclass shape
itself so this can't silently break the same way again.
"""
from __future__ import annotations

import pytest

from pooldash_app import langelier
from pooldash_app.db import lsi_history


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "lsi_test.sqlite3")


def test_lsi_result_has_no_dict_get():
    """Regression guard: LSIResult is a dataclass, not a dict."""
    result = langelier.lsi_from_values(
        ph=7.5, temperature_c=28.0,
        calcium_hardness_mgL_as_CaCO3=250, total_alkalinity_mgL_as_CaCO3=100,
        tds_mgL=1000,
    )
    assert not hasattr(result, "get")
    assert hasattr(result, "lsi")
    assert hasattr(result, "ph_saturation")


def test_calculation_round_trips_through_storage(db_path):
    result = langelier.lsi_from_values(
        ph=7.5, temperature_c=28.0,
        calcium_hardness_mgL_as_CaCO3=250, total_alkalinity_mgL_as_CaCO3=100,
        tds_mgL=1000,
    )

    lsi_history.store_lsi_reading(
        pool="PoolA",
        lsi_value=result.lsi,
        ph=7.5,
        temperature_c=28.0,
        calcium_hardness=250,
        total_alkalinity=100,
        tds=1000,
        ph_saturation=result.ph_saturation,
        source="manual",
        db_path=db_path,
    )

    latest = lsi_history.get_latest_lsi("PoolA", db_path=db_path)
    assert latest is not None
    assert latest["lsi_value"] == pytest.approx(result.lsi)
    assert latest["ph_saturation"] == pytest.approx(result.ph_saturation)
    assert latest["source"] == "manual"


def test_multiple_readings_ordered_newest_first(db_path):
    for ph in (7.2, 7.4, 7.6):
        result = langelier.lsi_from_values(
            ph=ph, temperature_c=28.0,
            calcium_hardness_mgL_as_CaCO3=250, total_alkalinity_mgL_as_CaCO3=100,
            tds_mgL=1000,
        )
        lsi_history.store_lsi_reading(
            pool="PoolA", lsi_value=result.lsi, ph=ph, temperature_c=28.0,
            calcium_hardness=250, total_alkalinity=100, tds=1000,
            ph_saturation=result.ph_saturation, db_path=db_path,
        )

    history = lsi_history.get_lsi_history("PoolA", limit=10, db_path=db_path)
    assert len(history) == 3
    assert [row["ph"] for row in history] == [7.6, 7.4, 7.2]


def test_chart_data_empty_until_a_reading_exists(db_path):
    timestamps, values = lsi_history.get_lsi_chart_data("PoolA", since_days=90, db_path=db_path)
    assert timestamps == []
    assert values == []

    result = langelier.lsi_from_values(
        ph=7.5, temperature_c=28.0,
        calcium_hardness_mgL_as_CaCO3=250, total_alkalinity_mgL_as_CaCO3=100,
        tds_mgL=1000,
    )
    lsi_history.store_lsi_reading(
        pool="PoolA", lsi_value=result.lsi, ph=7.5, temperature_c=28.0,
        calcium_hardness=250, total_alkalinity=100, tds=1000,
        ph_saturation=result.ph_saturation, db_path=db_path,
    )

    timestamps, values = lsi_history.get_lsi_chart_data("PoolA", since_days=90, db_path=db_path)
    assert len(timestamps) == 1
    assert values[0] == pytest.approx(result.lsi)
