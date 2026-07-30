"""Validation for the v6.11.23 `chromium_scale_factor` setting.

Added alongside `screen_rotation`'s pattern to let the kiosk browser
compensate for high-DPI touchscreens (e.g. the 10" official panel, ~226dpi,
vs the 7" screen's ~132dpi the UI was originally tuned for). Unlike
`screen_rotation`, this value has no settings-page route - it's set by
hand-editing `pooldash_settings.json` on the Pi - so persist.py's validation
is the only thing standing between a typo and an unvalidated
`--force-device-scale-factor` value reaching the kiosk Chromium launch
(see deploy/labwc_autostart). See persist.py DEFAULTS / load().

persist.py imports `fcntl` at module scope (POSIX file locking), so this
test only runs where fcntl exists - the Pi and Linux CI. It skips on
Windows dev machines.
"""
import json

import pytest

pytest.importorskip("fcntl")  # persist.py is POSIX-only (fcntl file locks)

from pooldash_app import persist  # noqa: E402  (after importorskip by design)


def _seed(tmp_path, data):
    (tmp_path / "pooldash_settings.json").write_text(json.dumps(data), encoding="utf-8")


def test_valid_scale_factor_persists_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)
    _seed(tmp_path, {"chromium_scale_factor": 1.5})

    loaded = persist.load(str(tmp_path))

    assert loaded["chromium_scale_factor"] == 1.5


@pytest.mark.parametrize("bad_value", [0.1, 4.1, -1, 10])
def test_out_of_range_scale_factor_clamps_to_default(tmp_path, monkeypatch, bad_value):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)
    _seed(tmp_path, {"chromium_scale_factor": bad_value})

    loaded = persist.load(str(tmp_path))

    assert loaded["chromium_scale_factor"] == persist.DEFAULTS["chromium_scale_factor"]


def test_non_numeric_scale_factor_clamps_to_default(tmp_path, monkeypatch):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)
    _seed(tmp_path, {"chromium_scale_factor": "big"})

    loaded = persist.load(str(tmp_path))

    assert loaded["chromium_scale_factor"] == persist.DEFAULTS["chromium_scale_factor"]


def test_bool_scale_factor_clamps_to_default(tmp_path, monkeypatch):
    # bool is a subclass of int in Python - True/False would otherwise pass
    # an isinstance(scale, (int, float)) check. This is the single most
    # valuable case to pin: it's the kind of guard a future "simplification"
    # would delete first, since it looks redundant without this test.
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)
    _seed(tmp_path, {"chromium_scale_factor": True})

    loaded = persist.load(str(tmp_path))

    assert loaded["chromium_scale_factor"] == persist.DEFAULTS["chromium_scale_factor"]


def test_missing_scale_factor_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)
    _seed(tmp_path, {})

    loaded = persist.load(str(tmp_path))

    assert loaded["chromium_scale_factor"] == persist.DEFAULTS["chromium_scale_factor"]
