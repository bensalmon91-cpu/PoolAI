"""Backward-compat for the 2026-06-12 remote_sync retirement.

Settings files written before remote_sync was removed still carry the
`remote_sync_*` keys. Loading such a file must not error, and saving it back
must drop the retired keys while preserving `remote_api_key` (still used by
every cloud upload). See persist.py DEFAULTS / load() / save().

persist.py imports `fcntl` at module scope (POSIX file locking), so this test
only runs where fcntl exists — the Pi and Linux CI, which is where the
on-device settings file actually lives. It skips on Windows dev machines.
"""
import json

import pytest

pytest.importorskip("fcntl")  # persist.py is POSIX-only (fcntl file locks)

from pooldash_app import persist  # noqa: E402  (after importorskip by design)


# A settings dict as written by a pre-2026-06-12 build: retired remote_sync_*
# keys present alongside the still-live remote_api_key.
OLD_SETTINGS = {
    "remote_sync_enabled": True,
    "remote_sync_url": "https://modprojects.co.uk",
    "remote_sync_schedule": "weekly",
    "remote_sync_interval_hours": 168,
    "last_remote_sync_ts": "2026-05-01 03:00:00",
    "remote_api_key": "deadbeef" * 8,
    "device_id": "test-device-uuid",
}

RETIRED_KEYS = (
    "remote_sync_enabled",
    "remote_sync_url",
    "remote_sync_schedule",
    "remote_sync_interval_hours",
    "last_remote_sync_ts",
)


def _seed(tmp_path, data):
    (tmp_path / "pooldash_settings.json").write_text(json.dumps(data), encoding="utf-8")


def test_old_settings_with_remote_sync_keys_load_without_error(tmp_path, monkeypatch):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)
    _seed(tmp_path, OLD_SETTINGS)

    loaded = persist.load(str(tmp_path))

    # Doesn't crash; the still-live keys come through intact.
    assert loaded["remote_api_key"] == OLD_SETTINGS["remote_api_key"]
    assert loaded["device_id"] == "test-device-uuid"


def test_save_drops_retired_remote_sync_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)

    persist.save(str(tmp_path), OLD_SETTINGS)
    on_disk = json.loads(
        (tmp_path / "pooldash_settings.json").read_text(encoding="utf-8")
    )

    for key in RETIRED_KEYS:
        assert key not in on_disk, f"retired key {key!r} should be dropped on save"
    # The key that survived the retirement is still persisted.
    assert on_disk["remote_api_key"] == OLD_SETTINGS["remote_api_key"]


def test_roundtrip_load_after_save_is_clean(tmp_path, monkeypatch):
    monkeypatch.delenv("POOLDASH_SETTINGS_PATH", raising=False)

    persist.save(str(tmp_path), OLD_SETTINGS)
    reloaded = persist.load(str(tmp_path))

    # After a save the file no longer carries the retired keys, so a fresh
    # load is free of them too (load() doesn't reintroduce them).
    for key in RETIRED_KEYS:
        assert key not in reloaded, f"retired key {key!r} resurfaced after save+load"
