#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Provision this PoolAIssistant_v6 device with the cloud backend.

Flow:
1) Collect MAC + device metadata
2) POST to /api/provision with bootstrap secret
3) Store device token locally for future uploads
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime, timezone

import requests


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def format_mac(node: int) -> str:
    return ":".join(f"{(node >> ele) & 0xFF:02x}" for ele in range(40, -1, -8))


def get_mac_address() -> str:
    node = uuid.getnode()
    return format_mac(node)


def load_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

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


def ensure_parent_dir(path: str) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def save_token(path: str, payload: dict) -> None:
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def main() -> int:
    backend = load_env("BACKEND_URL") or load_settings_value("backend_url")
    bootstrap = load_env("BOOTSTRAP_SECRET") or load_settings_value("bootstrap_secret")
    token_path = load_env("DEVICE_TOKEN_PATH", "/opt/PoolAIssistant/data/device_token.json")
    model = load_env("DEVICE_MODEL", "PoolAIssistant_v6")
    software_version = load_env("SOFTWARE_VERSION", "")

    if not backend:
        print("BACKEND_URL is required")
        return 1
    if not bootstrap:
        print("BOOTSTRAP_SECRET is required")
        return 1

    mac = get_mac_address()
    hostname = socket.gethostname()

    url = backend.rstrip("/") + "/api/provision"
    payload = {
        "mac": mac,
        "hostname": hostname,
        "model": model,
        "softwareVersion": software_version,
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"x-bootstrap-secret": bootstrap},
            timeout=10,
        )
    except requests.RequestException as exc:
        print(f"Provision failed: {exc}")
        return 1

    if resp.status_code != 200:
        print(f"Provision failed: {resp.status_code} {resp.text}")
        return 1

    data = resp.json()
    token_payload = {
        "deviceId": data.get("deviceId", ""),
        "token": data.get("token", ""),
        "mac": mac,
        "backend": backend,
        "provisionedAt": utc_now_iso(),
    }

    if not token_payload["deviceId"] or not token_payload["token"]:
        print("Provision failed: missing token or deviceId")
        return 1

    save_token(token_path, token_payload)
    print(f"Provisioned device {token_payload['deviceId']}")
    print(f"Token saved to {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
