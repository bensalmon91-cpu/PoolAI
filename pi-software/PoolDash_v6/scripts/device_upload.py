#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Upload PoolAIssistant_v6 data to the cloud backend.

Default mode is delta upload of new readings from the local SQLite DB.
If UPLOAD_MODE=file, uploads the full file to /api/device/upload instead.
"""

from __future__ import annotations

import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import requests


def load_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_token(token_path: str) -> dict:
    if not os.path.exists(token_path):
        return {}
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_status(path: str, status: str, message: str) -> None:
    if not path:
        return
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {
        "status": status,
        "message": message,
        "updatedAt": utc_now_iso(),
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def ensure_provisioned(token_path: str) -> dict:
    token_data = load_token(token_path)
    if token_data.get("token") and token_data.get("deviceId") and token_data.get("backend"):
        return token_data

    script_dir = Path(__file__).resolve().parent
    provisioner = script_dir / "device_provision.py"
    if not provisioner.exists():
        return {}

    result = os.system(f"python3 \"{provisioner}\"")
    if result != 0:
        return {}

    return load_token(token_path)


def load_state(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_settings_value(key: str) -> str:
    settings_path = load_env("POOLDASH_SETTINGS_PATH", "/opt/PoolAIssistant/data/pooldash_settings.json")
    if not settings_path or not os.path.exists(settings_path):
        return ""
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get(key, "") or "").strip()
    except Exception:
        return ""

def load_settings_interval() -> int:
    settings_path = load_env("POOLDASH_SETTINGS_PATH", "/opt/PoolAIssistant/data/pooldash_settings.json")
    if not settings_path or not os.path.exists(settings_path):
        return 0
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        value = int(data.get("upload_interval_minutes", 0))
        return value
    except Exception:
        return 0


def save_state(path: str, state: dict) -> None:
    if not path:
        return
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def fetch_readings(db_path: str, since_ts: str, limit: int) -> list[dict]:
    con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        if since_ts:
            rows = cur.execute(
                """
                SELECT ts, pool, host, system_name, serial_number, point_label, value, raw_type
                FROM readings
                WHERE ts > ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (since_ts, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT ts, pool, host, system_name, serial_number, point_label, value, raw_type
                FROM readings
                ORDER BY ts ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()

def fetch_alarm_events(db_path: str, since_ts: str, limit: int) -> list[dict]:
    con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        if since_ts:
            rows = cur.execute(
                """
                SELECT started_ts, ended_ts, pool, host, system_name, serial_number, source_label, bit_name
                FROM alarm_events
                WHERE started_ts > ?
                ORDER BY started_ts ASC
                LIMIT ?
                """,
                (since_ts, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT started_ts, ended_ts, pool, host, system_name, serial_number, source_label, bit_name
                FROM alarm_events
                ORDER BY started_ts ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def upload_delta(backend: str, token: str, db_path: str, state_path: str, batch_size: int) -> bool:
    last_ts = load_state(state_path).get("last_ts", "")
    url = backend.rstrip("/") + "/api/device/readings"

    while True:
        rows = fetch_readings(db_path, last_ts, batch_size)
        if not rows:
            return True

        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"rows": rows},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"backend upload failed ({exc})")

        if resp.status_code != 200:
            raise RuntimeError(f"backend upload failed: {resp.status_code} {resp.text}")

        last_ts = rows[-1]["ts"]
        save_state(state_path, {"last_ts": last_ts, "updatedAt": utc_now_iso()})


def upload_file(backend: str, token: str, file_path: Path) -> bool:
    url = backend.rstrip("/") + "/api/device/upload"
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (file_path.name, f, "application/octet-stream")},
                timeout=20,
            )
    except requests.RequestException as exc:
        raise RuntimeError(f"backend upload failed ({exc})")

    if resp.status_code != 200:
        raise RuntimeError(f"backend upload failed: {resp.status_code} {resp.text}")
    return True


def upload_alarm_delta(backend: str, token: str, db_path: str, state_path: str, batch_size: int) -> None:
    state = load_state(state_path)
    last_ts = state.get("last_alarm_ts", "")
    url = backend.rstrip("/") + "/api/device/alarms"

    while True:
        rows = fetch_alarm_events(db_path, last_ts, batch_size)
        if not rows:
            return
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"rows": rows},
            timeout=20,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"alarm upload failed: {resp.status_code} {resp.text}")
        last_ts = rows[-1]["started_ts"]
        state["last_alarm_ts"] = last_ts
        state["updatedAt"] = utc_now_iso()
        save_state(state_path, state)


def main() -> int:
    token_path = load_env("DEVICE_TOKEN_PATH", "/opt/PoolAIssistant/data/device_token.json")
    data_path = load_env("POOLDB", "/opt/PoolAIssistant/data/pool_readings.sqlite3")
    status_path = load_env("BACKEND_STATUS_PATH", "/opt/PoolAIssistant/data/backend_status.json")
    state_path = load_env("UPLOAD_STATE_PATH", "/opt/PoolAIssistant/data/upload_state.json")
    upload_mode = load_env("UPLOAD_MODE", "delta").lower()
    batch_size = int(load_env("UPLOAD_BATCH_SIZE", "500"))
    interval_minutes = load_settings_interval()
    if interval_minutes <= 0:
        try:
            interval_minutes = int(load_env("UPLOAD_INTERVAL_MINUTES", "0"))
        except Exception:
            interval_minutes = 0

    if len(sys.argv) > 1:
        data_path = sys.argv[1]

    token_data = ensure_provisioned(token_path)
    token = token_data.get("token", "")
    backend = token_data.get("backend", "") or load_settings_value("backend_url")

    if not token or not backend:
        message = "WARNING: device not provisioned or backend missing. Will retry on next run."
        print(message)
        write_status(status_path, "warning", message)
        return 0

    if interval_minutes > 0:
        state = load_state(state_path)
        last_run = state.get("last_upload_at")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60.0
                if elapsed < interval_minutes:
                    message = f"Skipping upload; next run in {int(interval_minutes - elapsed)} min."
                    write_status(status_path, "ok", message)
                    return 0
            except Exception:
                pass

    file_path = Path(data_path)
    if not file_path.exists():
        message = f"WARNING: data file not found: {file_path}"
        print(message)
        write_status(status_path, "warning", message)
        return 0

    try:
        if upload_mode == "file":
            upload_file(backend, token, file_path)
        else:
            upload_delta(backend, token, str(file_path), state_path, batch_size)
            upload_alarm_delta(backend, token, str(file_path), state_path, batch_size)
    except Exception as exc:
        message = f"WARNING: {exc}. Will retry on next run."
        print(message)
        write_status(status_path, "warning", message)
        return 0

    state = load_state(state_path)
    state["last_upload_at"] = utc_now_iso()
    save_state(state_path, state)
    write_status(status_path, "ok", "Upload successful")
    print("Upload successful")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
